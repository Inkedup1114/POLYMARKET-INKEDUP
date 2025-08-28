#!/usr/bin/env python3
"""
Scanner Dashboard Integration

Integrates the real-time visual dashboard with the existing Polymarket scanner
to provide live trading opportunity visualization with real market data.

This module bridges the gap between:
- The existing Scanner class and its strategies
- The new VisualTradingDashboard for real-time display
- Live market data and order book information
- Trading signal generation and opportunity detection
"""

import asyncio
import logging
from typing import Any

from .cached_scanner import CachedScanner
from .config import BotConfig
from .signals import SpreadSignal
from .strategies.alerts import WideSpreadAlertStrategy
from .strategies.complement import ComplementArbStrategy
from .visual_trading_dashboard import TradingOpportunity, VisualTradingDashboard
from .web_trading_dashboard import WebTradingDashboard

logger = logging.getLogger("scanner_dashboard_integration")


class IntegratedTradingDashboard(VisualTradingDashboard):
    """
    Integrated dashboard that uses real scanner data from the Polymarket bot.

    This class extends VisualTradingDashboard to work with the existing
    scanner infrastructure and live market data.
    """

    def __init__(self, config: BotConfig):
        """Initialize integrated dashboard with real scanner."""
        super().__init__(config)

        # Use the cached scanner for better performance
        self.scanner = CachedScanner(config)

        # Initialize strategies for opportunity detection
        self.strategies = []

        # Add spread alert strategy
        if config.spread_alert_bps > 0:
            self.spread_strategy = WideSpreadAlertStrategy(config.spread_alert_bps)
            self.strategies.append(self.spread_strategy)

        # Add complement arbitrage strategy
        self.complement_strategy = ComplementArbStrategy(
            min_deviation_threshold=config.complement_arb_min_deviation,
            max_deviation_threshold=config.complement_arb_max_deviation,
            base_trade_size=config.complement_arb_base_size,
            max_trade_size=config.complement_arb_max_size,
            size_scaling_factor=config.complement_arb_size_scaling,
        )
        self.strategies.append(self.complement_strategy)

        logger.info("Integrated trading dashboard initialized with real scanner")

    async def _run_scanner(self) -> None:
        """Override scanner to use real market data and strategies."""
        logger.info("Starting integrated scanner with live market data...")

        while True:
            try:
                scan_start_time = asyncio.get_event_loop().time()

                # Ensure markets are loaded
                await self.scanner.ensure_markets()
                markets = self.scanner._markets_cache

                if not markets:
                    logger.warning("No markets available, waiting...")
                    await asyncio.sleep(10)
                    continue

                # Process markets in batches to avoid overwhelming the API
                batch_size = 10
                new_opportunities = []

                for i in range(
                    0, min(len(markets), 50), batch_size
                ):  # Limit to 50 markets for performance
                    batch = markets[i : i + batch_size]
                    batch_opportunities = await self._process_market_batch(batch)
                    new_opportunities.extend(batch_opportunities)

                    # Small delay between batches to respect rate limits
                    if i + batch_size < len(markets):
                        await asyncio.sleep(0.5)

                # Update opportunities in dashboard
                self._update_opportunities(new_opportunities)
                self._update_stats()

                # Calculate scan performance metrics
                scan_duration = asyncio.get_event_loop().time() - scan_start_time
                self.scan_times.append(scan_duration)

                logger.info(
                    f"Integrated scan completed: {len(new_opportunities)} opportunities "
                    f"found in {scan_duration:.2f}s across {len(markets)} markets"
                )

                # Adaptive sleep based on market activity and performance
                sleep_time = self._calculate_adaptive_scan_interval(
                    len(new_opportunities)
                )
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Integrated scanner error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retry

    async def _process_market_batch(
        self, markets: list[dict[str, Any]]
    ) -> list[TradingOpportunity]:
        """Process a batch of markets for trading opportunities."""
        opportunities = []

        # Process markets concurrently within the batch
        tasks = [self._analyze_market_integrated(market) for market in markets]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in batch_results:
            if isinstance(result, Exception):
                logger.error(f"Market analysis error: {result}")
                continue
            if isinstance(result, list):
                opportunities.extend(result)

        return opportunities

    async def _analyze_market_integrated(
        self, market: dict[str, Any]
    ) -> list[TradingOpportunity]:
        """Analyze a single market using integrated scanner strategies."""
        opportunities = []

        try:
            market_slug = market.get("slug", "")
            if not market_slug:
                return opportunities

            # Use scanner to get market composite data
            try:
                market_composites = await self.scanner.scan_once(top=50)
                for composite in market_composites:
                    if composite.market_slug == market_slug:
                        # Process each token in the market composite
                        for token_id, token_data in composite.tokens.items():
                            token_opportunities = await self._analyze_token_integrated(
                                market, token_data, token_id
                            )
                            opportunities.extend(token_opportunities)
                        break
            except Exception as e:
                logger.debug(f"Failed to scan market {market_slug}: {e}")
                return opportunities

        except Exception as e:
            logger.error(
                f"Error in integrated market analysis for {market.get('slug', 'unknown')}: {e}"
            )

        return opportunities

    async def _analyze_token_integrated(
        self, market: dict[str, Any], token_data: dict[str, Any], token_id: str
    ) -> list[TradingOpportunity]:
        """Analyze a single token using integrated strategies."""
        opportunities = []

        try:
            market_slug = market.get("slug", "")
            market_title = market.get("question", "Unknown Market")
            token_id = token_data.get("token_id", "")
            outcome = token_data.get("outcome", "Unknown")

            # Get order book data
            bids = token_data.get("bids", [])
            asks = token_data.get("asks", [])

            if not bids or not asks:
                return opportunities

            # Calculate basic pricing metrics
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 1.0
            mid_price = (best_bid + best_ask) / 2
            spread_bps = (
                int((best_ask - best_bid) * 10000) if best_ask > best_bid else 0
            )

            # Calculate liquidity metrics using existing calculator
            liquidity_metrics = await self._calculate_integrated_liquidity(bids, asks)

            # Run through each strategy to detect opportunities

            # 1. Wide Spread Strategy
            if hasattr(self, "spread_strategy"):
                spread_signals = await self._check_spread_opportunities(
                    market,
                    token_data,
                    best_bid,
                    best_ask,
                    spread_bps,
                    liquidity_metrics,
                )
                opportunities.extend(spread_signals)

            # 2. Complement Arbitrage Strategy
            if hasattr(self, "complement_strategy"):
                complement_opportunities = (
                    await self._check_complement_opportunities_integrated(
                        market, token_data, best_bid, best_ask, liquidity_metrics
                    )
                )
                opportunities.extend(complement_opportunities)

            # 3. Market Making Opportunities (if enabled)
            if self.config.mm_enabled:
                mm_opportunities = await self._check_market_making_integrated(
                    market, token_data, best_bid, best_ask, liquidity_metrics
                )
                opportunities.extend(mm_opportunities)

        except Exception as e:
            logger.error(
                f"Error analyzing token {token_data.get('token_id', 'unknown')}: {e}"
            )

        return opportunities

    async def _calculate_integrated_liquidity(
        self, bids: list[dict], asks: list[dict]
    ) -> dict[str, float]:
        """Calculate liquidity metrics using the integrated liquidity calculator."""
        try:
            # Use existing liquidity calculator if available
            if hasattr(self, "liquidity_calculator") and self.liquidity_calculator:
                # Convert bid/ask data to format expected by calculator
                bid_data = [
                    (float(bid["price"]), float(bid["size"])) for bid in bids[:10]
                ]
                ask_data = [
                    (float(ask["price"]), float(ask["size"])) for ask in asks[:10]
                ]

                # Calculate liquidity score
                liquidity_score = (
                    await self.liquidity_calculator.calculate_liquidity_score(
                        bid_data, ask_data
                    )
                )

                # Calculate total available liquidity
                total_bid_liquidity = sum(
                    float(bid["price"]) * float(bid["size"]) for bid in bids[:10]
                )
                total_ask_liquidity = sum(
                    float(ask["price"]) * float(ask["size"]) for ask in asks[:10]
                )
                total_liquidity = total_bid_liquidity + total_ask_liquidity

            else:
                # Fallback calculation if liquidity calculator not available
                total_liquidity = sum(
                    float(bid["price"]) * float(bid["size"]) for bid in bids[:10]
                ) + sum(float(ask["price"]) * float(ask["size"]) for ask in asks[:10])
                liquidity_score = min(1.0, total_liquidity / 50000)  # Normalize to $50k

            # Calculate slippage for different trade sizes
            slippage_1k = self._calculate_slippage(asks, 1000) if asks else 0.0
            slippage_5k = self._calculate_slippage(asks, 5000) if asks else 0.0
            slippage_10k = self._calculate_slippage(asks, 10000) if asks else 0.0

            # Market impact estimation
            market_impact = max(0, (slippage_5k - slippage_1k) * 2)

            return {
                "score": liquidity_score,
                "total_liquidity": total_liquidity,
                "slippage_1k": slippage_1k,
                "slippage_5k": slippage_5k,
                "slippage_10k": slippage_10k,
                "market_impact": market_impact,
            }

        except Exception as e:
            logger.error(f"Error calculating integrated liquidity: {e}")
            return {
                "score": 0.0,
                "total_liquidity": 0.0,
                "slippage_1k": 0.0,
                "slippage_5k": 0.0,
                "slippage_10k": 0.0,
                "market_impact": 0.0,
            }

    async def _check_spread_opportunities(
        self,
        market: dict[str, Any],
        token_data: dict[str, Any],
        best_bid: float,
        best_ask: float,
        spread_bps: int,
        liquidity_metrics: dict[str, float],
    ) -> list[TradingOpportunity]:
        """Check for wide spread opportunities using the integrated strategy."""
        opportunities = []

        try:
            if spread_bps >= self.config.spread_alert_bps:
                # Create spread signal for the strategy
                spread_signal = SpreadSignal(
                    market_slug=market.get("slug", ""),
                    token_id=token_data.get("token_id", ""),
                    bid=best_bid,
                    ask=best_ask,
                    spread_bps=spread_bps,
                    strategy="wide_spread_alert",
                )

                # Calculate opportunity metrics
                confidence = self._calculate_confidence(spread_bps, liquidity_metrics)
                expected_profit = self._estimate_spread_profit(
                    spread_bps, liquidity_metrics
                )
                recommended_size = self._calculate_position_size(
                    "wide_spread", spread_bps, liquidity_metrics
                )

                opportunity = TradingOpportunity(
                    market_slug=market.get("slug", ""),
                    market_title=market.get("question", "Unknown Market"),
                    token_id=token_data.get("token_id", ""),
                    outcome_name=token_data.get("outcome", "Unknown"),
                    opportunity_type="wide_spread",
                    signal_strength=min(1.0, spread_bps / 2000),
                    bid_price=best_bid,
                    ask_price=best_ask,
                    mid_price=(best_bid + best_ask) / 2,
                    spread_bps=spread_bps,
                    expected_profit=expected_profit,
                    liquidity_score=liquidity_metrics["score"],
                    available_liquidity=liquidity_metrics["total_liquidity"],
                    slippage_1k=liquidity_metrics["slippage_1k"],
                    slippage_5k=liquidity_metrics["slippage_5k"],
                    slippage_10k=liquidity_metrics["slippage_10k"],
                    market_impact=liquidity_metrics["market_impact"],
                    confidence=confidence,
                    risk_score=self._calculate_risk_score(
                        spread_bps, liquidity_metrics
                    ),
                    discovered_at=asyncio.get_event_loop().time(),
                    last_updated=asyncio.get_event_loop().time(),
                    recommended_size=recommended_size,
                    entry_price=best_ask,  # Buy at ask for spread play
                    target_exit=best_ask + (best_ask - best_bid) * 0.5,
                    stop_loss=best_ask - (best_ask - best_bid) * 0.2,
                )

                opportunities.append(opportunity)

        except Exception as e:
            logger.error(f"Error checking spread opportunities: {e}")

        return opportunities

    async def _check_complement_opportunities_integrated(
        self,
        market: dict[str, Any],
        token_data: dict[str, Any],
        best_bid: float,
        best_ask: float,
        liquidity_metrics: dict[str, float],
    ) -> list[TradingOpportunity]:
        """Check for complement arbitrage opportunities using integrated strategy."""
        opportunities = []

        try:
            # Only check binary markets for complement arbitrage
            market_tokens = market.get("tokens", [])
            if len(market_tokens) != 2:
                return opportunities

            # Find the complement token
            current_token_id = token_data.get("token_id", "")
            complement_token = None
            for token in market_tokens:
                if token.get("token_id") != current_token_id:
                    complement_token = token
                    break

            if not complement_token:
                return opportunities

            # Get complement token pricing
            complement_bids = complement_token.get("bids", [])
            complement_asks = complement_token.get("asks", [])

            if not complement_bids or not complement_asks:
                return opportunities

            complement_best_bid = float(complement_bids[0]["price"])
            complement_best_ask = float(complement_asks[0]["price"])
            complement_mid = (complement_best_bid + complement_best_ask) / 2

            # Calculate deviation from theoretical complement pricing
            current_mid = (best_bid + best_ask) / 2
            theoretical_complement = 1.0 - current_mid
            actual_complement = complement_mid
            deviation = abs(theoretical_complement - actual_complement)

            # Check if deviation meets threshold
            if deviation >= self.config.complement_arb_min_deviation:
                # Determine which side to trade
                if actual_complement > theoretical_complement:
                    # Complement is overpriced, buy current token, sell complement
                    signal_strength = (
                        deviation / self.config.complement_arb_max_deviation
                    )
                else:
                    # Current token is overpriced, sell current, buy complement
                    signal_strength = (
                        deviation / self.config.complement_arb_max_deviation
                    )

                # Calculate profit potential
                expected_profit = deviation * self._calculate_position_size(
                    "complement_arb", 0, liquidity_metrics
                )
                confidence = min(
                    1.0, deviation / 0.05
                )  # Higher confidence for larger deviations

                opportunity = TradingOpportunity(
                    market_slug=market.get("slug", ""),
                    market_title=market.get("question", "Unknown Market"),
                    token_id=current_token_id,
                    outcome_name=token_data.get("outcome", "Unknown"),
                    opportunity_type="complement_arb",
                    signal_strength=min(1.0, signal_strength),
                    bid_price=best_bid,
                    ask_price=best_ask,
                    mid_price=current_mid,
                    spread_bps=int((best_ask - best_bid) * 10000),
                    complement_token_id=complement_token.get("token_id", ""),
                    complement_price=complement_mid,
                    deviation=deviation,
                    expected_profit=expected_profit,
                    liquidity_score=liquidity_metrics["score"],
                    available_liquidity=liquidity_metrics["total_liquidity"],
                    slippage_1k=liquidity_metrics["slippage_1k"],
                    slippage_5k=liquidity_metrics["slippage_5k"],
                    slippage_10k=liquidity_metrics["slippage_10k"],
                    market_impact=liquidity_metrics["market_impact"],
                    confidence=confidence,
                    risk_score=self._calculate_risk_score(0, liquidity_metrics),
                    discovered_at=asyncio.get_event_loop().time(),
                    last_updated=asyncio.get_event_loop().time(),
                    recommended_size=self._calculate_position_size(
                        "complement_arb", 0, liquidity_metrics
                    ),
                )

                opportunities.append(opportunity)

        except Exception as e:
            logger.error(f"Error checking complement opportunities: {e}")

        return opportunities

    async def _check_market_making_integrated(
        self,
        market: dict[str, Any],
        token_data: dict[str, Any],
        best_bid: float,
        best_ask: float,
        liquidity_metrics: dict[str, float],
    ) -> list[TradingOpportunity]:
        """Check for market making opportunities using integrated data."""
        opportunities = []

        try:
            spread_bps = int((best_ask - best_bid) * 10000)

            # Only create MM opportunities for reasonable spreads
            if (
                self.config.mm_min_spread_bps
                <= spread_bps
                <= self.config.mm_max_spread_bps
                and liquidity_metrics["score"] > 0.3
            ):  # Minimum liquidity requirement

                mid_price = (best_bid + best_ask) / 2
                expected_profit = self._estimate_mm_profit(
                    spread_bps, liquidity_metrics
                )
                confidence = (
                    liquidity_metrics["score"] * 0.8
                )  # MM confidence based on liquidity

                opportunity = TradingOpportunity(
                    market_slug=market.get("slug", ""),
                    market_title=market.get("question", "Unknown Market"),
                    token_id=token_data.get("token_id", ""),
                    outcome_name=token_data.get("outcome", "Unknown"),
                    opportunity_type="market_making",
                    signal_strength=liquidity_metrics["score"],
                    bid_price=best_bid,
                    ask_price=best_ask,
                    mid_price=mid_price,
                    spread_bps=spread_bps,
                    expected_profit=expected_profit,
                    liquidity_score=liquidity_metrics["score"],
                    available_liquidity=liquidity_metrics["total_liquidity"],
                    slippage_1k=liquidity_metrics["slippage_1k"],
                    slippage_5k=liquidity_metrics["slippage_5k"],
                    slippage_10k=liquidity_metrics["slippage_10k"],
                    market_impact=liquidity_metrics["market_impact"],
                    confidence=confidence,
                    risk_score=self._calculate_risk_score(
                        spread_bps, liquidity_metrics
                    ),
                    discovered_at=asyncio.get_event_loop().time(),
                    last_updated=asyncio.get_event_loop().time(),
                    recommended_size=self._calculate_position_size(
                        "market_making", spread_bps, liquidity_metrics
                    ),
                )

                opportunities.append(opportunity)

        except Exception as e:
            logger.error(f"Error checking market making opportunities: {e}")

        return opportunities

    def _calculate_adaptive_scan_interval(self, opportunities_found: int) -> float:
        """Calculate adaptive scan interval based on market activity."""
        base_interval = 10.0  # Base scan interval in seconds

        # Faster scanning with more opportunities
        if opportunities_found > 20:
            return base_interval * 0.5  # 5 seconds
        elif opportunities_found > 10:
            return base_interval * 0.7  # 7 seconds
        elif opportunities_found > 5:
            return base_interval  # 10 seconds
        else:
            return base_interval * 1.5  # 15 seconds


class IntegratedWebDashboard(WebTradingDashboard):
    """Web dashboard integrated with real scanner data."""

    def __init__(self, config: BotConfig, port: int = 8080):
        """Initialize integrated web dashboard."""
        super().__init__(config, port)

        # Replace dashboard with integrated version
        self.dashboard = IntegratedTradingDashboard(config)

        logger.info("Integrated web dashboard initialized")


# Convenience functions for easy use
async def run_integrated_dashboard(config: BotConfig | None = None) -> None:
    """Run the integrated visual dashboard with real scanner data.

    Args:
        config: Bot configuration, will create default if not provided
    """
    if config is None:
        config = BotConfig()

    dashboard = IntegratedTradingDashboard(config)
    await dashboard.start_dashboard()


async def run_integrated_web_dashboard(
    config: BotConfig | None = None, port: int = 8080
) -> None:
    """Run the integrated web dashboard with real scanner data.

    Args:
        config: Bot configuration
        port: Web server port
    """
    if config is None:
        config = BotConfig()

    dashboard = IntegratedWebDashboard(config, port)
    await dashboard.start_server()


logger.info("Scanner dashboard integration module loaded successfully")
