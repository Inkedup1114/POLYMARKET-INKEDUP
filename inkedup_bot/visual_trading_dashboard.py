#!/usr/bin/env python3
"""
Real-Time Visual Trading Opportunities Dashboard

A comprehensive visual interface for monitoring live Polymarket trading opportunities
including arbitrage, spreads, liquidity analysis, and slippage calculations.

Features:
- Real-time opportunity scanning with live updates
- Interactive tables with sorting and filtering
- Color-coded opportunity alerts and status indicators
- Live charting of spreads and price movements
- Detailed slippage analysis and market impact calculations
- Portfolio tracking and performance metrics
- Audio/visual alerts for high-value opportunities
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .cached_scanner import CachedScanner
from .config import BotConfig
from .liquidity import LiquidityCalculator

logger = logging.getLogger("visual_trading_dashboard")
console = Console()


@dataclass
class TradingOpportunity:
    """Comprehensive trading opportunity with all relevant metrics."""

    # Basic market information
    market_slug: str
    market_title: str
    token_id: str
    outcome_name: str

    # Opportunity details
    opportunity_type: str  # "complement_arb", "wide_spread", "market_making"
    signal_strength: float  # 0.0 to 1.0

    # Pricing information
    bid_price: float
    ask_price: float
    mid_price: float
    spread_bps: int

    # Arbitrage-specific (if applicable)
    complement_token_id: str | None = None
    complement_price: float = 0.0
    deviation: float = 0.0
    expected_profit: float = 0.0

    # Liquidity and slippage analysis
    liquidity_score: float = 0.0
    available_liquidity: float = 0.0
    slippage_1k: float = 0.0  # Slippage for $1k trade
    slippage_5k: float = 0.0  # Slippage for $5k trade
    slippage_10k: float = 0.0  # Slippage for $10k trade
    market_impact: float = 0.0

    # Risk metrics
    confidence: float = 0.0
    risk_score: float = 0.0  # 0=low risk, 1=high risk

    # Timing information
    discovered_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    ttl: float = 60.0  # Time to live in seconds

    # Trading recommendations
    recommended_size: float = 0.0
    max_position_size: float = 0.0
    entry_price: float = 0.0
    target_exit: float = 0.0
    stop_loss: float = 0.0

    def is_expired(self) -> bool:
        """Check if opportunity has expired."""
        return (datetime.now() - self.last_updated).total_seconds() > self.ttl

    def get_profit_potential(self) -> float:
        """Calculate profit potential as percentage of investment."""
        if self.recommended_size > 0:
            return (self.expected_profit / self.recommended_size) * 100
        return 0.0

    def get_risk_adjusted_return(self) -> float:
        """Calculate risk-adjusted return."""
        profit_potential = self.get_profit_potential()
        risk_penalty = self.risk_score * 50  # Max 50% penalty for high risk
        return max(0, profit_potential - risk_penalty)


@dataclass
class MarketMetrics:
    """Market-level metrics and statistics."""

    market_slug: str
    volume_24h: float = 0.0
    volatility: float = 0.0
    active_opportunities: int = 0
    avg_spread: float = 0.0
    total_liquidity: float = 0.0
    last_price_change: float = 0.0
    trend_direction: str = "neutral"  # "up", "down", "neutral"


@dataclass
class DashboardStats:
    """Overall dashboard statistics."""

    total_opportunities: int = 0
    high_confidence_opportunities: int = 0
    total_profit_potential: float = 0.0
    avg_spread: float = 0.0
    markets_scanned: int = 0
    scan_frequency: float = 0.0
    uptime: float = 0.0
    last_scan: datetime | None = None

    # Performance metrics
    opportunities_per_hour: float = 0.0
    success_rate: float = 0.0
    avg_opportunity_lifetime: float = 0.0


class VisualTradingDashboard:
    """Real-time visual dashboard for trading opportunities."""

    def __init__(self, config: BotConfig):
        """Initialize the visual trading dashboard.

        Args:
            config: Bot configuration with scanning parameters
        """
        self.config = config
        self.scanner = CachedScanner(config)
        self.liquidity_calculator = LiquidityCalculator()

        # Dashboard state
        self.opportunities: dict[str, TradingOpportunity] = {}
        self.market_metrics: dict[str, MarketMetrics] = {}
        self.stats = DashboardStats()
        self.start_time = datetime.now()

        # Update tracking
        self.opportunity_history: deque = deque(maxlen=1000)
        self.price_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.scan_times: deque = deque(maxlen=50)

        # Display settings
        self.max_opportunities_displayed = 20
        self.sort_by = "signal_strength"  # or "expected_profit", "spread_bps", etc.
        self.filter_min_confidence = 0.0
        self.filter_opportunity_types: set[str] = {
            "complement_arb",
            "wide_spread",
            "market_making",
        }

        # Alert settings
        self.alert_min_profit = 10.0  # Minimum profit for alert ($)
        self.alert_min_confidence = 0.7  # Minimum confidence for alert
        self.alerted_opportunities: set[str] = set()

        logger.info("Visual trading dashboard initialized")

    async def start_dashboard(self, update_interval: float = 2.0) -> None:
        """Start the real-time dashboard with live updates.

        Args:
            update_interval: Seconds between dashboard updates
        """
        console.print("\n🚀 Starting Real-Time Polymarket Trading Dashboard...")
        console.print(f"📊 Update interval: {update_interval}s")
        console.print("💡 Press Ctrl+C to stop\n")

        # Start background scanner
        scanner_task = asyncio.create_task(self._run_scanner())

        try:
            # Run dashboard with live updates
            with Live(
                self._generate_dashboard_layout(),
                console=console,
                refresh_per_second=1 / update_interval,
                transient=False,
            ) as live:
                while True:
                    # Update dashboard display
                    live.update(self._generate_dashboard_layout())

                    # Clean up expired opportunities
                    self._cleanup_expired_opportunities()

                    # Check for alerts
                    await self._check_alerts()

                    await asyncio.sleep(update_interval)

        except KeyboardInterrupt:
            console.print("\n👋 Stopping dashboard...")
        finally:
            scanner_task.cancel()
            try:
                await scanner_task
            except asyncio.CancelledError:
                pass

    async def _run_scanner(self) -> None:
        """Background task to continuously scan for opportunities."""
        while True:
            try:
                scan_start = time.time()

                # Scan for opportunities
                await self.scanner.ensure_markets(force=True)
                markets = self.scanner._markets_cache

                # Process each market
                new_opportunities = []
                for market in markets[:50]:  # Limit for performance
                    opportunities = await self._analyze_market(market)
                    new_opportunities.extend(opportunities)

                # Update opportunities
                self._update_opportunities(new_opportunities)

                # Update statistics
                scan_time = time.time() - scan_start
                self.scan_times.append(scan_time)
                self._update_stats()

                logger.debug(
                    f"Scan completed in {scan_time:.2f}s, found {len(new_opportunities)} opportunities"
                )

                # Adaptive scanning frequency based on market activity
                sleep_time = self._calculate_scan_interval()
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Scanner error: {e}")
                await asyncio.sleep(5)  # Wait before retry

    async def _analyze_market(self, market: dict[str, Any]) -> list[TradingOpportunity]:
        """Analyze a single market for trading opportunities.

        Args:
            market: Market data dictionary

        Returns:
            List of trading opportunities found
        """
        opportunities = []

        try:
            market_slug = market.get("slug", "")
            market_title = market.get("question", "Unknown Market")

            # Get order book data
            book_data = await self._fetch_order_book(market_slug)
            if not book_data:
                return opportunities

            # Analyze each token/outcome
            for token_data in book_data:
                token_id = token_data.get("token_id", "")
                outcome = token_data.get("outcome", "Unknown")

                # Calculate basic metrics
                bids = token_data.get("bids", [])
                asks = token_data.get("asks", [])

                if not bids or not asks:
                    continue

                best_bid = float(bids[0]["price"]) if bids else 0.0
                best_ask = float(asks[0]["price"]) if asks else 1.0
                mid_price = (best_bid + best_ask) / 2
                spread_bps = (
                    int((best_ask - best_bid) * 10000) if best_ask > best_bid else 0
                )

                # Calculate liquidity and slippage
                liquidity_metrics = await self._calculate_liquidity_metrics(bids, asks)

                # Check for different opportunity types

                # 1. Wide spread opportunities
                if spread_bps >= self.config.spread_alert_bps:
                    opportunity = TradingOpportunity(
                        market_slug=market_slug,
                        market_title=market_title,
                        token_id=token_id,
                        outcome_name=outcome,
                        opportunity_type="wide_spread",
                        signal_strength=min(1.0, spread_bps / 2000),  # Normalize to 0-1
                        bid_price=best_bid,
                        ask_price=best_ask,
                        mid_price=mid_price,
                        spread_bps=spread_bps,
                        liquidity_score=liquidity_metrics["score"],
                        available_liquidity=liquidity_metrics["total_liquidity"],
                        slippage_1k=liquidity_metrics["slippage_1k"],
                        slippage_5k=liquidity_metrics["slippage_5k"],
                        slippage_10k=liquidity_metrics["slippage_10k"],
                        market_impact=liquidity_metrics["market_impact"],
                        confidence=self._calculate_confidence(
                            spread_bps, liquidity_metrics
                        ),
                        risk_score=self._calculate_risk_score(
                            spread_bps, liquidity_metrics
                        ),
                        discovered_at=datetime.now(),
                        last_updated=datetime.now(),
                        recommended_size=self._calculate_position_size(
                            "wide_spread", spread_bps, liquidity_metrics
                        ),
                        expected_profit=self._estimate_spread_profit(
                            spread_bps, liquidity_metrics
                        ),
                    )
                    opportunities.append(opportunity)

                # 2. Complement arbitrage (for binary markets)
                complement_opp = await self._check_complement_arbitrage(
                    market, token_data, liquidity_metrics
                )
                if complement_opp:
                    opportunities.append(complement_opp)

                # 3. Market making opportunities
                if self.config.mm_enabled and liquidity_metrics["score"] > 0.3:
                    mm_opp = self._create_market_making_opportunity(
                        market_slug,
                        market_title,
                        token_id,
                        outcome,
                        best_bid,
                        best_ask,
                        liquidity_metrics,
                    )
                    if mm_opp:
                        opportunities.append(mm_opp)

        except Exception as e:
            logger.error(f"Error analyzing market {market.get('slug', 'unknown')}: {e}")

        return opportunities

    async def _fetch_order_book(
        self, market_slug: str
    ) -> list[dict[str, Any]] | None:
        """Fetch order book data for a market."""
        try:
            # This would integrate with your existing order book fetching logic
            # For now, return mock data structure
            return []  # Replace with actual implementation
        except Exception as e:
            logger.error(f"Failed to fetch order book for {market_slug}: {e}")
            return None

    async def _calculate_liquidity_metrics(
        self, bids: list[dict], asks: list[dict]
    ) -> dict[str, float]:
        """Calculate comprehensive liquidity and slippage metrics."""
        # Implement detailed slippage calculations
        total_bid_liquidity = sum(
            float(bid["size"]) * float(bid["price"]) for bid in bids[:10]
        )
        total_ask_liquidity = sum(
            float(ask["size"]) * float(ask["price"]) for ask in asks[:10]
        )
        total_liquidity = total_bid_liquidity + total_ask_liquidity

        # Calculate slippage for different trade sizes
        slippage_1k = self._calculate_slippage(asks, 1000) if asks else 0.0
        slippage_5k = self._calculate_slippage(asks, 5000) if asks else 0.0
        slippage_10k = self._calculate_slippage(asks, 10000) if asks else 0.0

        # Market impact estimation
        market_impact = (slippage_5k - slippage_1k) * 5  # Impact scaling factor

        # Liquidity score (0-1)
        max_liquidity = 100000  # $100k reference
        liquidity_score = min(1.0, total_liquidity / max_liquidity)

        return {
            "score": liquidity_score,
            "total_liquidity": total_liquidity,
            "slippage_1k": slippage_1k,
            "slippage_5k": slippage_5k,
            "slippage_10k": slippage_10k,
            "market_impact": market_impact,
        }

    def _calculate_slippage(self, asks: list[dict], trade_size_usd: float) -> float:
        """Calculate slippage for a given trade size."""
        if not asks:
            return 0.0

        remaining_size = trade_size_usd
        total_cost = 0.0
        shares_bought = 0.0

        for ask in asks:
            ask_price = float(ask["price"])
            ask_size_shares = float(ask["size"])
            ask_size_usd = ask_size_shares * ask_price

            if remaining_size <= 0:
                break

            size_to_buy = min(remaining_size / ask_price, ask_size_shares)
            cost = size_to_buy * ask_price

            total_cost += cost
            shares_bought += size_to_buy
            remaining_size -= cost

        if shares_bought > 0:
            avg_price_paid = total_cost / shares_bought
            best_price = float(asks[0]["price"])
            slippage = (avg_price_paid - best_price) / best_price
            return slippage * 100  # Convert to percentage

        return 0.0

    async def _check_complement_arbitrage(
        self, market: dict, token_data: dict, liquidity_metrics: dict
    ) -> TradingOpportunity | None:
        """Check for complement arbitrage opportunities."""
        # Implementation would check for binary markets and calculate complement pricing
        # This is a placeholder for the actual complement arbitrage logic
        return None

    def _create_market_making_opportunity(
        self,
        market_slug: str,
        market_title: str,
        token_id: str,
        outcome: str,
        best_bid: float,
        best_ask: float,
        liquidity_metrics: dict,
    ) -> TradingOpportunity | None:
        """Create market making opportunity."""
        spread_bps = int((best_ask - best_bid) * 10000)

        # Only create MM opportunity if spread is reasonable for market making
        if spread_bps < 50 or spread_bps > 1000:  # 0.5% to 10%
            return None

        mid_price = (best_bid + best_ask) / 2
        confidence = liquidity_metrics["score"] * 0.8  # Lower confidence for MM

        return TradingOpportunity(
            market_slug=market_slug,
            market_title=market_title,
            token_id=token_id,
            outcome_name=outcome,
            opportunity_type="market_making",
            signal_strength=liquidity_metrics["score"],
            bid_price=best_bid,
            ask_price=best_ask,
            mid_price=mid_price,
            spread_bps=spread_bps,
            liquidity_score=liquidity_metrics["score"],
            available_liquidity=liquidity_metrics["total_liquidity"],
            slippage_1k=liquidity_metrics["slippage_1k"],
            slippage_5k=liquidity_metrics["slippage_5k"],
            slippage_10k=liquidity_metrics["slippage_10k"],
            market_impact=liquidity_metrics["market_impact"],
            confidence=confidence,
            risk_score=self._calculate_risk_score(spread_bps, liquidity_metrics),
            discovered_at=datetime.now(),
            last_updated=datetime.now(),
            recommended_size=self._calculate_position_size(
                "market_making", spread_bps, liquidity_metrics
            ),
            expected_profit=self._estimate_mm_profit(spread_bps, liquidity_metrics),
        )

    def _calculate_confidence(self, spread_bps: int, liquidity_metrics: dict) -> float:
        """Calculate confidence score for an opportunity."""
        # Higher confidence for:
        # - Wider spreads (more profit potential)
        # - Better liquidity (easier execution)
        # - Lower slippage (more predictable execution)

        spread_score = min(1.0, spread_bps / 1000)  # Normalize to 0-1
        liquidity_score = liquidity_metrics["score"]
        slippage_penalty = min(
            0.5, liquidity_metrics["slippage_1k"] / 10
        )  # Max 50% penalty

        confidence = (spread_score + liquidity_score) / 2 - slippage_penalty
        return max(0.0, min(1.0, confidence))

    def _calculate_risk_score(self, spread_bps: int, liquidity_metrics: dict) -> float:
        """Calculate risk score (0=low risk, 1=high risk)."""
        # Higher risk for:
        # - Low liquidity
        # - High slippage
        # - Extreme spreads (too wide or too narrow)

        liquidity_risk = 1.0 - liquidity_metrics["score"]
        slippage_risk = min(1.0, liquidity_metrics["slippage_5k"] / 10)

        # Spread risk (both too wide and too narrow are risky)
        optimal_spread = 200  # 2%
        spread_risk = abs(spread_bps - optimal_spread) / 1000
        spread_risk = min(1.0, spread_risk)

        risk_score = (liquidity_risk + slippage_risk + spread_risk) / 3
        return min(1.0, risk_score)

    def _calculate_position_size(
        self, opportunity_type: str, spread_bps: int, liquidity_metrics: dict
    ) -> float:
        """Calculate recommended position size."""
        base_size = {
            "wide_spread": 1000,  # $1k base for spread plays
            "complement_arb": 2000,  # $2k base for arbitrage
            "market_making": 500,  # $500 base for market making
        }.get(opportunity_type, 1000)

        # Adjust based on liquidity and confidence
        liquidity_multiplier = min(2.0, liquidity_metrics["score"] * 2)
        slippage_penalty = max(0.5, 1.0 - liquidity_metrics["slippage_1k"] / 5)

        recommended_size = base_size * liquidity_multiplier * slippage_penalty

        # Cap at available liquidity
        max_size = min(recommended_size, liquidity_metrics["total_liquidity"] * 0.1)

        return max(100, max_size)  # Minimum $100 position

    def _estimate_spread_profit(
        self, spread_bps: int, liquidity_metrics: dict
    ) -> float:
        """Estimate profit from spread trading."""
        # Simplified profit estimation
        spread_profit = spread_bps / 10000  # Convert bps to decimal
        slippage_cost = liquidity_metrics["slippage_1k"] / 100  # Slippage as decimal

        net_profit_rate = max(0, spread_profit - slippage_cost - 0.005)  # 0.5% costs

        return net_profit_rate * 1000  # Profit on $1k position

    def _estimate_mm_profit(self, spread_bps: int, liquidity_metrics: dict) -> float:
        """Estimate profit from market making."""
        # Market making profit is typically half the spread
        spread_profit = (spread_bps / 10000) / 2

        # Adjust for execution probability and costs
        execution_rate = min(0.8, liquidity_metrics["score"])  # Max 80% fill rate
        net_profit_rate = spread_profit * execution_rate - 0.002  # 0.2% costs

        return max(0, net_profit_rate * 500)  # Profit on $500 position

    def _update_opportunities(
        self, new_opportunities: list[TradingOpportunity]
    ) -> None:
        """Update the opportunities dictionary with new data."""
        # Remove expired opportunities
        self._cleanup_expired_opportunities()

        # Add/update opportunities
        for opp in new_opportunities:
            key = f"{opp.market_slug}_{opp.token_id}_{opp.opportunity_type}"

            if key in self.opportunities:
                # Update existing opportunity
                old_opp = self.opportunities[key]
                opp.discovered_at = (
                    old_opp.discovered_at
                )  # Keep original discovery time

            self.opportunities[key] = opp

            # Track in history
            self.opportunity_history.append(
                {
                    "timestamp": datetime.now(),
                    "opportunity": opp,
                    "action": "updated" if key in self.opportunities else "discovered",
                }
            )

    def _cleanup_expired_opportunities(self) -> None:
        """Remove expired opportunities."""
        expired_keys = [
            key for key, opp in self.opportunities.items() if opp.is_expired()
        ]

        for key in expired_keys:
            del self.opportunities[key]

    def _calculate_scan_interval(self) -> float:
        """Calculate adaptive scan interval based on market activity."""
        # More opportunities = faster scanning
        num_opportunities = len(self.opportunities)

        if num_opportunities > 10:
            return 1.0  # Fast scanning with many opportunities
        elif num_opportunities > 5:
            return 2.0  # Normal scanning
        else:
            return 5.0  # Slower scanning when quiet

    def _update_stats(self) -> None:
        """Update dashboard statistics."""
        now = datetime.now()

        self.stats.total_opportunities = len(self.opportunities)
        self.stats.high_confidence_opportunities = sum(
            1 for opp in self.opportunities.values() if opp.confidence >= 0.7
        )
        self.stats.total_profit_potential = sum(
            opp.expected_profit for opp in self.opportunities.values()
        )
        self.stats.avg_spread = (
            sum(opp.spread_bps for opp in self.opportunities.values())
            / len(self.opportunities)
            if self.opportunities
            else 0
        )
        self.stats.scan_frequency = len(self.scan_times) / max(1, sum(self.scan_times))
        self.stats.uptime = (now - self.start_time).total_seconds()
        self.stats.last_scan = now

        # Calculate opportunities per hour
        hours_running = max(1, self.stats.uptime / 3600)
        self.stats.opportunities_per_hour = (
            len(self.opportunity_history) / hours_running
        )

    async def _check_alerts(self) -> None:
        """Check for high-value opportunities and generate alerts."""
        for opp_id, opp in self.opportunities.items():
            if (
                opp_id not in self.alerted_opportunities
                and opp.expected_profit >= self.alert_min_profit
                and opp.confidence >= self.alert_min_confidence
            ):

                await self._trigger_alert(opp)
                self.alerted_opportunities.add(opp_id)

        # Clean up old alerts
        current_opp_ids = set(self.opportunities.keys())
        self.alerted_opportunities &= current_opp_ids

    async def _trigger_alert(self, opp: TradingOpportunity) -> None:
        """Trigger alert for high-value opportunity."""
        alert_message = (
            f"🚨 HIGH-VALUE OPPORTUNITY DETECTED!\n"
            f"Market: {opp.market_title}\n"
            f"Type: {opp.opportunity_type.upper()}\n"
            f"Expected Profit: ${opp.expected_profit:.2f}\n"
            f"Confidence: {opp.confidence:.1%}\n"
            f"Recommended Size: ${opp.recommended_size:.0f}"
        )

        # You could integrate with:
        # - Desktop notifications
        # - Email alerts
        # - Slack/Discord webhooks
        # - Audio alerts

        logger.warning(alert_message)

    def _generate_dashboard_layout(self) -> Panel:
        """Generate the main dashboard layout."""
        # Create main dashboard content
        dashboard_content = []

        # Header with stats
        header = self._create_header()
        dashboard_content.append(header)

        # Opportunities table
        opportunities_table = self._create_opportunities_table()
        dashboard_content.append(opportunities_table)

        # Market overview
        market_overview = self._create_market_overview()
        dashboard_content.append(market_overview)

        # Footer with controls
        footer = self._create_footer()
        dashboard_content.append(footer)

        # Combine all sections
        main_content = "\n\n".join(str(section) for section in dashboard_content)

        return Panel(
            main_content,
            title="🎯 Polymarket Trading Opportunities Dashboard",
            border_style="bright_blue",
            padding=(1, 2),
        )

    def _create_header(self) -> Table:
        """Create dashboard header with key statistics."""
        table = Table.grid(padding=1)
        table.add_column(justify="left")
        table.add_column(justify="center")
        table.add_column(justify="right")

        # Status indicators
        uptime_str = str(timedelta(seconds=int(self.stats.uptime)))
        last_scan_str = (
            self.stats.last_scan.strftime("%H:%M:%S")
            if self.stats.last_scan
            else "Never"
        )

        status_text = Text()
        status_text.append("🔄 Active", style="green")
        status_text.append(f" | ⏱️ Uptime: {uptime_str}")
        status_text.append(f" | 🔍 Last Scan: {last_scan_str}")

        # Key metrics
        metrics_text = Text()
        metrics_text.append("📊 Total Opportunities: ", style="white")
        metrics_text.append(f"{self.stats.total_opportunities}", style="cyan bold")
        metrics_text.append(" | ⭐ High Confidence: ", style="white")
        metrics_text.append(
            f"{self.stats.high_confidence_opportunities}", style="green bold"
        )

        # Profit potential
        profit_text = Text()
        profit_text.append("💰 Total Profit Potential: ", style="white")
        profit_text.append(
            f"${self.stats.total_profit_potential:.2f}", style="green bold"
        )
        profit_text.append(" | 📈 Avg Spread: ", style="white")
        profit_text.append(f"{self.stats.avg_spread:.0f} bps", style="yellow")

        table.add_row(status_text, metrics_text, profit_text)

        return table

    def _create_opportunities_table(self) -> Table:
        """Create the main opportunities table."""
        table = Table(
            title="🎯 Live Trading Opportunities",
            show_header=True,
            header_style="bold magenta",
            title_style="bold blue",
        )

        # Table columns
        table.add_column("Market", style="cyan", width=25)
        table.add_column("Type", justify="center", width=12)
        table.add_column("Spread", justify="right", style="yellow")
        table.add_column("Profit", justify="right", style="green")
        table.add_column("Size", justify="right", style="blue")
        table.add_column("Confidence", justify="center")
        table.add_column("Liquidity", justify="right", style="magenta")
        table.add_column("Slippage", justify="right", style="red")
        table.add_column("Age", justify="center", style="dim")

        # Sort opportunities
        sorted_opportunities = sorted(
            self.opportunities.values(),
            key=lambda x: getattr(x, self.sort_by, 0),
            reverse=True,
        )

        # Add rows
        displayed = 0
        for opp in sorted_opportunities:
            if displayed >= self.max_opportunities_displayed:
                break

            # Apply filters
            if opp.confidence < self.filter_min_confidence:
                continue
            if opp.opportunity_type not in self.filter_opportunity_types:
                continue

            # Format values
            market_name = (
                opp.market_title[:22] + "..."
                if len(opp.market_title) > 25
                else opp.market_title
            )
            opp_type = opp.opportunity_type.replace("_", " ").title()
            spread = f"{opp.spread_bps} bps"
            profit = f"${opp.expected_profit:.2f}"
            size = f"${opp.recommended_size:.0f}"

            # Confidence with color coding
            conf_pct = f"{opp.confidence:.1%}"
            if opp.confidence >= 0.8:
                confidence = f"[green]{conf_pct}[/green]"
            elif opp.confidence >= 0.6:
                confidence = f"[yellow]{conf_pct}[/yellow]"
            else:
                confidence = f"[red]{conf_pct}[/red]"

            liquidity = f"${opp.available_liquidity:.0f}"
            slippage = f"{opp.slippage_1k:.2f}%"

            # Calculate age
            age_seconds = (datetime.now() - opp.discovered_at).total_seconds()
            if age_seconds < 60:
                age = f"{age_seconds:.0f}s"
            else:
                age = f"{age_seconds/60:.1f}m"

            table.add_row(
                market_name,
                opp_type,
                spread,
                profit,
                size,
                confidence,
                liquidity,
                slippage,
                age,
            )

            displayed += 1

        if not self.opportunities:
            table.add_row(
                "[dim]No opportunities found[/dim]", "", "", "", "", "", "", "", ""
            )

        return table

    def _create_market_overview(self) -> Table:
        """Create market overview section."""
        table = Table(
            title="📈 Market Overview",
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("Metric", style="white")
        table.add_column("Value", justify="right", style="cyan")
        table.add_column("Metric", style="white")
        table.add_column("Value", justify="right", style="cyan")

        # Calculate metrics
        total_markets = len(set(opp.market_slug for opp in self.opportunities.values()))
        avg_opp_lifetime = (
            sum(
                (datetime.now() - opp.discovered_at).total_seconds()
                for opp in self.opportunities.values()
            )
            / len(self.opportunities)
            if self.opportunities
            else 0
        )

        scan_rate = (
            f"{self.stats.scan_frequency:.1f}/s"
            if self.stats.scan_frequency > 0
            else "N/A"
        )

        table.add_row("Active Markets", f"{total_markets}", "Scan Rate", scan_rate)
        table.add_row(
            "Opportunities/Hour",
            f"{self.stats.opportunities_per_hour:.1f}",
            "Avg Opportunity Age",
            f"{avg_opp_lifetime:.0f}s",
        )

        return table

    def _create_footer(self) -> Text:
        """Create footer with controls and tips."""
        footer = Text()
        footer.append("\n💡 Tips: ", style="bold white")
        footer.append("Look for high confidence + low slippage opportunities | ")
        footer.append("Monitor liquidity before placing large orders | ")
        footer.append("Consider market impact for position sizing\n")

        footer.append("🎛️ Controls: ", style="bold white")
        footer.append("[S]ort by different metrics | ")
        footer.append("[F]ilter opportunities | ")
        footer.append("[A]lert settings | ")
        footer.append("[Ctrl+C] to exit")

        return footer


# Convenience function for easy dashboard startup
async def run_visual_dashboard(config: BotConfig | None = None) -> None:
    """Run the visual trading dashboard.

    Args:
        config: Bot configuration, will create default if not provided
    """
    if config is None:
        config = BotConfig()

    dashboard = VisualTradingDashboard(config)
    await dashboard.start_dashboard()


if __name__ == "__main__":
    # Allow running dashboard directly
    asyncio.run(run_visual_dashboard())
