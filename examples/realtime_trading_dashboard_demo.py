#!/usr/bin/env python3
"""
Real-Time Trading Dashboard Demo

Demonstrates the visual trading opportunities dashboard with:
- Live market scanning and opportunity detection
- Real-time updates with slippage calculations
- Interactive command-line interface
- Web dashboard integration
- Mock data generation for testing
"""

import asyncio
import logging
import random
import webbrowser
from datetime import datetime, timedelta

from inkedup_bot.config import BotConfig
from inkedup_bot.visual_trading_dashboard import (
    TradingOpportunity,
    VisualTradingDashboard,
)
from inkedup_bot.web_trading_dashboard import WebTradingDashboard

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class MockTradingDashboardDemo:
    """Demo class that generates mock trading opportunities for testing."""

    def __init__(self):
        """Initialize the demo with mock data generation."""
        self.config = BotConfig(
            # Demo configuration
            spread_alert_bps=100,
            complement_arb_min_deviation=0.02,
            mm_enabled=True,
            market_cache_ttl=60,
        )

        # Sample markets for demo
        self.sample_markets = [
            {
                "slug": "2024-presidential-election",
                "title": "2024 Presidential Election Winner",
                "outcomes": ["Republican", "Democrat", "Other"],
            },
            {
                "slug": "fed-rate-hike-december",
                "title": "Fed Rate Hike in December 2024",
                "outcomes": ["Yes", "No"],
            },
            {
                "slug": "bitcoin-price-100k",
                "title": "Bitcoin to reach $100k by End of 2024",
                "outcomes": ["Yes", "No"],
            },
            {
                "slug": "nfl-superbowl-winner",
                "title": "NFL Super Bowl 2024 Winner",
                "outcomes": ["Chiefs", "Bills", "Ravens", "Other"],
            },
            {
                "slug": "stock-market-crash",
                "title": "S&P 500 to drop 20% in 2024",
                "outcomes": ["Yes", "No"],
            },
        ]

    def generate_mock_opportunities(self) -> list[TradingOpportunity]:
        """Generate realistic mock trading opportunities."""
        opportunities = []

        for market in self.sample_markets:
            for outcome in market["outcomes"]:
                # Randomly generate different types of opportunities
                opportunity_types = ["complement_arb", "wide_spread", "market_making"]
                opp_type = random.choice(opportunity_types)

                # Generate realistic pricing data
                base_price = random.uniform(0.20, 0.80)
                spread_width = random.uniform(0.02, 0.15)  # 2-15% spread

                bid_price = max(0.01, base_price - spread_width / 2)
                ask_price = min(0.99, base_price + spread_width / 2)
                mid_price = (bid_price + ask_price) / 2
                spread_bps = int((ask_price - bid_price) * 10000)

                # Generate liquidity metrics
                liquidity_score = random.uniform(0.3, 1.0)
                available_liquidity = random.uniform(5000, 100000)

                # Calculate slippage based on liquidity
                base_slippage = random.uniform(0.1, 2.0)
                slippage_1k = base_slippage * (1 - liquidity_score * 0.5)
                slippage_5k = slippage_1k * 1.5
                slippage_10k = slippage_1k * 2.2

                # Generate opportunity-specific metrics
                if opp_type == "complement_arb":
                    deviation = random.uniform(0.01, 0.08)
                    expected_profit = deviation * random.uniform(1000, 5000)
                    confidence = min(
                        1.0, deviation * 20
                    )  # Higher deviation = higher confidence
                    signal_strength = min(1.0, deviation * 15)

                elif opp_type == "wide_spread":
                    expected_profit = (spread_bps / 10000) * random.uniform(500, 2000)
                    confidence = min(
                        1.0, spread_bps / 2000
                    )  # Higher spread = higher confidence
                    signal_strength = min(1.0, spread_bps / 1500)

                else:  # market_making
                    expected_profit = (
                        (spread_bps / 10000) * 0.5 * random.uniform(300, 1000)
                    )
                    confidence = (
                        liquidity_score * 0.8
                    )  # MM confidence depends on liquidity
                    signal_strength = liquidity_score

                # Risk score (inverse of confidence with some randomness)
                risk_score = max(
                    0.0, min(1.0, 1.0 - confidence + random.uniform(-0.2, 0.2))
                )

                # Position sizing
                recommended_size = min(
                    expected_profit * random.uniform(10, 50),  # Size based on profit
                    available_liquidity * 0.1,  # Max 10% of liquidity
                )
                recommended_size = max(100, recommended_size)  # Minimum $100

                # Only create opportunity if it meets minimum criteria
                if (
                    spread_bps >= 50
                    and expected_profit >= 5.0
                    and confidence >= 0.1
                    and random.random() > 0.3
                ):  # 70% chance

                    opportunity = TradingOpportunity(
                        market_slug=market["slug"],
                        market_title=market["title"],
                        token_id=f"0x{random.randint(1000000, 9999999):07x}",
                        outcome_name=outcome,
                        opportunity_type=opp_type,
                        signal_strength=signal_strength,
                        bid_price=bid_price,
                        ask_price=ask_price,
                        mid_price=mid_price,
                        spread_bps=spread_bps,
                        complement_token_id=(
                            f"0x{random.randint(1000000, 9999999):07x}"
                            if opp_type == "complement_arb"
                            else None
                        ),
                        complement_price=(
                            1.0 - mid_price if opp_type == "complement_arb" else 0.0
                        ),
                        deviation=deviation if opp_type == "complement_arb" else 0.0,
                        expected_profit=expected_profit,
                        liquidity_score=liquidity_score,
                        available_liquidity=available_liquidity,
                        slippage_1k=slippage_1k,
                        slippage_5k=slippage_5k,
                        slippage_10k=slippage_10k,
                        market_impact=slippage_5k - slippage_1k,
                        confidence=confidence,
                        risk_score=risk_score,
                        discovered_at=datetime.now()
                        - timedelta(seconds=random.randint(0, 300)),
                        last_updated=datetime.now(),
                        recommended_size=recommended_size,
                        max_position_size=recommended_size * 2,
                        entry_price=ask_price if random.random() > 0.5 else bid_price,
                        target_exit=(
                            ask_price * 1.1
                            if random.random() > 0.5
                            else bid_price * 0.9
                        ),
                        stop_loss=(
                            ask_price * 0.95
                            if random.random() > 0.5
                            else bid_price * 1.05
                        ),
                    )

                    opportunities.append(opportunity)

        return opportunities


class MockVisualDashboard(VisualTradingDashboard):
    """Modified visual dashboard that uses mock data for demo purposes."""

    def __init__(self, config: BotConfig):
        """Initialize with mock data generator."""
        super().__init__(config)
        self.demo = MockTradingDashboardDemo()
        logger.info("Mock visual dashboard initialized with demo data")

    async def _run_scanner(self) -> None:
        """Override scanner to use mock data."""
        while True:
            try:
                # Generate mock opportunities
                mock_opportunities = self.demo.generate_mock_opportunities()

                # Update opportunities
                self._update_opportunities(mock_opportunities)

                # Update statistics
                self._update_stats()

                # Log scan results
                logger.info(
                    f"Mock scan completed: {len(mock_opportunities)} opportunities generated"
                )

                # Variable scan interval for demo (faster updates)
                sleep_time = random.uniform(3, 8)  # 3-8 seconds
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Mock scanner error: {e}")
                await asyncio.sleep(5)


async def demo_console_dashboard():
    """Run the console-based visual dashboard demo."""
    print("🎯 Starting Console Trading Dashboard Demo...")
    print("💡 This demonstrates real-time opportunity scanning with mock data")
    print("🔄 Press Ctrl+C to stop\n")

    config = BotConfig(
        spread_alert_bps=100,
        complement_arb_min_deviation=0.02,
        mm_enabled=True,
    )

    dashboard = MockVisualDashboard(config)
    await dashboard.start_dashboard(update_interval=1.5)


async def demo_web_dashboard():
    """Run the web-based dashboard demo."""
    print("🌐 Starting Web Trading Dashboard Demo...")
    print("💡 This will open a web interface with interactive charts and tables")

    config = BotConfig(
        spread_alert_bps=100,
        complement_arb_min_deviation=0.02,
        mm_enabled=True,
    )

    class MockWebDashboard(WebTradingDashboard):
        """Web dashboard with mock data."""

        def __init__(self, config: BotConfig, port: int = 8080):
            super().__init__(config, port)
            # Replace the scanner with mock version
            self.dashboard = MockVisualDashboard(config)

    # Start web dashboard
    web_dashboard = MockWebDashboard(config, port=8080)

    # Open browser after a delay
    async def open_browser():
        await asyncio.sleep(3)
        webbrowser.open("http://localhost:8080")
        print("\n🌐 Web dashboard opened in your browser!")
        print("📊 You should see real-time trading opportunities updating")
        print("💡 Try filtering and sorting the opportunities")
        print("🎛️ Use the controls to customize the display")

    browser_task = asyncio.create_task(open_browser())

    try:
        await web_dashboard.start_server()
    except KeyboardInterrupt:
        print("\n👋 Stopping web dashboard demo...")
        browser_task.cancel()


async def demo_combined_dashboard():
    """Run both console and web dashboards simultaneously."""
    print("🚀 Starting Combined Dashboard Demo...")
    print("📊 Console dashboard will show in terminal")
    print("🌐 Web dashboard will open in browser")
    print("\n⚡ Both will update with the same mock data in real-time")

    config = BotConfig(
        spread_alert_bps=100,
        complement_arb_min_deviation=0.02,
        mm_enabled=True,
    )

    # Create shared mock dashboard
    mock_dashboard = MockVisualDashboard(config)

    # Start both dashboards
    console_task = asyncio.create_task(
        mock_dashboard.start_dashboard(update_interval=2.0)
    )

    # Web dashboard (simplified for demo)
    web_dashboard = WebTradingDashboard(config, port=8080)
    web_dashboard.dashboard = mock_dashboard  # Share the same dashboard instance
    web_task = asyncio.create_task(web_dashboard.start_server())

    # Open browser
    async def open_browser():
        await asyncio.sleep(3)
        webbrowser.open("http://localhost:8080")
        print("\n🌐 Web dashboard opened! Both dashboards are now running.")

    browser_task = asyncio.create_task(open_browser())

    try:
        # Wait for either task to complete (or Ctrl+C)
        await asyncio.gather(console_task, web_task, browser_task)
    except KeyboardInterrupt:
        print("\n👋 Stopping combined dashboard demo...")
        console_task.cancel()
        web_task.cancel()
        browser_task.cancel()


async def main():
    """Main demo function with menu selection."""
    print("🎯 Polymarket Real-Time Trading Dashboard Demo")
    print("=" * 50)
    print()
    print("This demo showcases the real-time visual trading opportunities dashboard")
    print("with live market scanning, slippage calculations, and interactive displays.")
    print()
    print("Available demo modes:")
    print("1. 📺 Console Dashboard - Terminal-based real-time display")
    print("2. 🌐 Web Dashboard - Interactive browser-based interface")
    print("3. 🚀 Combined Mode - Both console and web dashboards")
    print("4. ℹ️  Show Feature Overview")
    print()

    while True:
        try:
            choice = input("Select demo mode (1-4) or 'q' to quit: ").strip().lower()

            if choice == "q" or choice == "quit":
                print("👋 Goodbye!")
                break
            elif choice == "1":
                await demo_console_dashboard()
                break
            elif choice == "2":
                await demo_web_dashboard()
                break
            elif choice == "3":
                await demo_combined_dashboard()
                break
            elif choice == "4":
                show_feature_overview()
            else:
                print("❌ Invalid choice. Please select 1-4 or 'q' to quit.")

        except KeyboardInterrupt:
            print("\n👋 Demo interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            break


def show_feature_overview():
    """Display comprehensive feature overview."""
    print("\n🎯 Polymarket Trading Dashboard Features")
    print("=" * 50)

    print("\n📊 REAL-TIME OPPORTUNITY SCANNING:")
    print("• Complement arbitrage detection with deviation analysis")
    print("• Wide spread alerts with configurable thresholds")
    print("• Market making opportunity identification")
    print("• Live market data integration with caching")
    print("• Adaptive scan frequency based on market activity")

    print("\n💰 ADVANCED ANALYTICS:")
    print("• Detailed slippage calculations ($1k, $5k, $10k trade sizes)")
    print("• Market impact assessment for position sizing")
    print("• Liquidity scoring and available depth analysis")
    print("• Risk-adjusted return calculations")
    print("• Confidence scoring based on market conditions")

    print("\n📈 VISUAL INTERFACES:")
    print("• Real-time console dashboard with color-coded alerts")
    print("• Interactive web interface with charts and graphs")
    print("• Sortable and filterable opportunity tables")
    print("• Live performance tracking and statistics")
    print("• Historical opportunity timeline and analytics")

    print("\n🎛️ SMART FEATURES:")
    print("• Automatic opportunity expiration and cleanup")
    print("• Alert system for high-value opportunities")
    print("• Position size recommendations based on Kelly criterion")
    print("• Market volatility detection and response")
    print("• Portfolio integration and tracking capabilities")

    print("\n⚡ TECHNICAL CAPABILITIES:")
    print("• WebSocket real-time updates for web interface")
    print("• Async/await architecture for high performance")
    print("• Comprehensive error handling and recovery")
    print("• Configurable scanning parameters and thresholds")
    print("• Integration with existing trading infrastructure")

    print("\n🔧 DEMO DATA FEATURES:")
    print("• Realistic mock market generation")
    print("• Dynamic opportunity creation and expiration")
    print("• Varied opportunity types and market conditions")
    print("• Configurable demo parameters and scenarios")
    print("• Safe testing environment for strategy development")

    print("\n💡 INTEGRATION EXAMPLES:")
    print("• Scanner integration with existing Polymarket infrastructure")
    print("• Order execution interface (placeholder implementation)")
    print("• Risk management system integration")
    print("• Performance tracking and reporting")
    print("• Configuration management and hot reloading")

    input("\nPress Enter to continue...")


if __name__ == "__main__":
    asyncio.run(main())
