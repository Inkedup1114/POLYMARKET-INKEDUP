"""Market scanner and opportunity detection system for Polymarket trading.

This module provides comprehensive market scanning capabilities to identify
trading opportunities across prediction markets. The Scanner class monitors
order books, calculates spreads, detects arbitrage opportunities, and generates
trading signals based on configured strategies.

Key Features:
    - Real-time market data scanning and caching
    - Multiple trading strategy implementations
    - Liquidity analysis and market depth calculation
    - Complement arbitrage detection
    - Wide spread alert generation
    - Market making signal generation
    - Performance tracking and metrics collection

The scanner supports multiple market scanning strategies:
    - Complement Arbitrage: Exploits price discrepancies between complementary outcomes
    - Wide Spread Alerts: Identifies markets with unusually wide bid-ask spreads
    - Market Making: Generates quotes for providing liquidity

Example:
    Basic scanner usage:

    >>> from inkedup_bot.config import BotConfig
    >>> from inkedup_bot.scanner import Scanner
    >>>
    >>> # Initialize with configuration
    >>> config = BotConfig(
    ...     spread_alert_bps=100,
    ...     complement_arb_min_deviation=0.02,
    ...     market_cache_ttl=300
    ... )
    >>> scanner = Scanner(config)
    >>>
    >>> # Run single scan
    >>> await scanner.scan_once()
    >>>
    >>> # Continuous scanning (runs until stopped)
    >>> await scanner.run()

Architecture:
    Scanner -> Strategies -> TradingEngine -> OrderClient

    The scanner feeds market data to strategies, which generate signals
    that are processed by the trading engine for execution.

Performance:
    The scanner uses configurable batching and caching to minimize API
    calls while maintaining real-time responsiveness to market changes.

"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from .config import BotConfig
from .engine import TradingEngine
from .liquidity import LiquidityCalculator, LiquidityConfig, LiquidityMethod
from .signals import ComplementSignal, SpreadSignal
from .strategies import ComplementArbStrategy, WideSpreadAlertStrategy
from .strategies.market_making import MarketMakingConfig, MarketMakingStrategy
from .utils import HTTPClient, best_bid_ask, calc_spread_bps, chunk, fetch_markets

log = logging.getLogger("scanner")


@dataclass(slots=True)
class BookEntry:
    """Order book entry for a single token/outcome.

    Represents the current best bid/ask prices and calculated spread
    for a specific token in a prediction market.

    Attributes:
        token_id: Unique identifier for the token/outcome
        bid: Best bid price (None if no bids available)
        ask: Best ask price (None if no asks available)
        spread_bps: Bid-ask spread in basis points (None if cannot calculate)

    Example:
        >>> entry = BookEntry(
        ...     token_id="0x123...",
        ...     bid=0.45,
        ...     ask=0.55,
        ...     spread_bps=1000  # 10% spread
        ... )

    """

    token_id: str
    bid: float | None
    ask: float | None
    spread_bps: float | None


@dataclass(slots=True)
class MarketComposite:
    """Composite market data for analysis and strategy execution.

    Aggregates order book data for all tokens in a market and includes
    calculated metrics like complement deviation for arbitrage detection.

    Attributes:
        slug: Market identifier/slug
        tokens: List of order book entries for each outcome
        complement_deviation: Price deviation from perfect complement (optional)
        max_spread_bps: Maximum spread across all tokens (for volatility assessment)
        avg_spread_bps: Average spread across all tokens
        volatility_score: Calculated volatility score (0.0-1.0) for adaptive scanning
        last_updated: Timestamp of last update for change detection

    Example:
        >>> market = MarketComposite(
        ...     slug="election-2024",
        ...     tokens=[
        ...         BookEntry("token1", 0.45, 0.55, 1000),
        ...         BookEntry("token2", 0.40, 0.50, 1000)
        ...     ],
        ...     complement_deviation=0.05,
        ...     volatility_score=0.8
        ... )

    """

    slug: str
    tokens: list[BookEntry]
    complement_deviation: float | None = None
    max_spread_bps: float | None = None
    avg_spread_bps: float | None = None
    volatility_score: float | None = None
    last_updated: float | None = None


class Scanner:
    """Market scanner for identifying trading opportunities on Polymarket.

    This class continuously monitors prediction markets to identify arbitrage
    opportunities, spread discrepancies, and other trading signals. It integrates
    multiple trading strategies and provides market data analysis capabilities.

    Key Features:
    - Real-time market data scanning and caching
    - Multiple trading strategy support (complement arbitrage, spread alerts)
    - Liquidity analysis and market depth calculations
    - Batch order book fetching for efficiency
    - Configurable scanning intervals and thresholds
    - Integration with trading engine for signal execution

    Supported Strategies:
    - Complement Arbitrage: Exploits price inefficiencies in binary markets
    - Wide Spread Alerts: Identifies markets with unusual bid-ask spreads
    - Market Making: Provides liquidity in targeted markets

    Example:
        >>> from inkedup_bot.config import BotConfig
        >>>
        >>> # Initialize scanner with custom configuration
        >>> cfg = BotConfig(
        ...     complement_arb_min_deviation=0.02,  # 2% minimum deviation
        ...     spread_alert_bps=100,  # Alert on 100+ bps spreads
        ...     market_cache_ttl=300   # 5-minute cache TTL
        ... )
        >>> scanner = Scanner(cfg)
        >>>
        >>> # Single scan for opportunities
        >>> composites = await scanner.scan_once(top=20)
        >>> for comp in composites:
        ...     if comp.complement_deviation and comp.complement_deviation > 0.05:
        ...         print(f"Arbitrage opportunity: {comp.slug}")
        >>>
        >>> # Continuous scanning loop
        >>> await scanner.loop(interval=30, top=15)

    Args:
        cfg: Bot configuration containing scanning parameters and strategy settings
             If None, uses default BotConfig()

    Attributes:
        cfg: Configuration settings
        client: HTTP client for API requests
        engine: Trading engine for executing signals
        strategies: List of active trading strategies
        liquidity_calculator: Tool for analyzing market liquidity

    """

    def __init__(self, cfg: BotConfig | None = None) -> None:
        self.cfg = cfg or BotConfig()

        # Create rate limiter if enabled
        rate_limiter = None
        if self.cfg.rate_limiting.enabled:
            from .rate_limiter import APIRateLimiter

            rate_limiter = APIRateLimiter(self.cfg.rate_limiting.default_config)

            # Configure endpoint-specific rate limits
            for (
                endpoint_type,
                config,
            ) in self.cfg.rate_limiting.endpoint_configs.items():
                rate_limiter.configure_endpoint(endpoint_type, config)

        self.client = HTTPClient(str(self.cfg.api_base), rate_limiter=rate_limiter)
        self._markets_cache: list[dict[str, Any]] = []
        self._markets_refreshed_at = 0.0
        self.engine = TradingEngine(self.cfg)
        self.strategies: list[Any] = []
        self.market_making_strategy: MarketMakingStrategy | None

        # Initialize liquidity calculator with fallback configuration
        liquidity_config = LiquidityConfig(
            method=LiquidityMethod(self.cfg.liquidity_method),
            top_n_levels=self.cfg.liquidity_top_n_levels,
            effective_spread_pct=self.cfg.liquidity_effective_spread_pct,
            min_price_threshold=self.cfg.liquidity_min_price_threshold,
            max_price_threshold=self.cfg.liquidity_max_price_threshold,
            cache_ttl_seconds=self.cfg.liquidity_cache_ttl_seconds,
            weight_decay_factor=self.cfg.liquidity_weight_decay_factor,
            # Enhanced fallback configuration
            fallback_enabled=self.cfg.liquidity_fallback_enabled,
            fallback_minimum=self.cfg.liquidity_fallback_minimum,
            fallback_market_average=self.cfg.liquidity_fallback_market_average,
            fallback_high_volume=self.cfg.liquidity_fallback_high_volume,
            api_timeout_seconds=self.cfg.liquidity_api_timeout_seconds,
            max_retries=self.cfg.liquidity_max_retries,
        )
        self.liquidity_calculator = LiquidityCalculator(liquidity_config)
        if self.cfg.spread_alert_bps > 0:
            self.strategies.append(WideSpreadAlertStrategy(self.cfg.spread_alert_bps))
        self.strategies.append(
            ComplementArbStrategy(
                min_deviation_threshold=self.cfg.complement_arb_min_deviation,
                max_deviation_threshold=self.cfg.complement_arb_max_deviation,
                base_trade_size=self.cfg.complement_arb_base_size,
                max_trade_size=self.cfg.complement_arb_max_size,
                size_scaling_factor=self.cfg.complement_arb_size_scaling,
            )
        )

        # Initialize market making strategy if enabled
        if self.cfg.mm_enabled:
            mm_config = MarketMakingConfig(
                target_spread_bps=self.cfg.mm_target_spread_bps,
                max_position_size=self.cfg.mm_max_position_size,
                quote_size=self.cfg.mm_quote_size,
                min_spread_bps=self.cfg.mm_min_spread_bps,
                max_spread_bps=self.cfg.mm_max_spread_bps,
                inventory_skew_factor=self.cfg.mm_inventory_skew_factor,
                edge_bps=self.cfg.mm_edge_bps,
                min_liquidity=self.cfg.mm_min_liquidity,
                enabled_markets=self.cfg.mm_enabled_markets or None,
            )
            self.market_making_strategy = MarketMakingStrategy(mm_config)
        else:
            self.market_making_strategy = None

        # Adaptive scanning configuration and state
        self.adaptive_scanning_enabled = True
        self.base_scan_interval = 30.0  # Normal scanning interval (seconds)
        self.fast_scan_interval = 5.0  # Fast scanning during high volatility
        self.slow_scan_interval = 60.0  # Slower scanning during quiet periods

        # Volatility thresholds for adaptive scanning
        self.high_volatility_threshold = 0.7  # Switch to fast scanning
        self.low_volatility_threshold = 0.2  # Switch to slow scanning

        # Market volatility tracking
        self.market_history: dict[str, list[float]] = {}  # Track complement deviations
        self.market_volatility_cache: dict[str, float] = {}  # Cached volatility scores
        self.global_volatility_score = 0.0
        self.scan_history: list[tuple[float, float]] = (
            []
        )  # (timestamp, volatility_score)

        # Adaptive scanning statistics
        self.adaptive_stats = {
            "total_scans": 0,
            "fast_scans": 0,
            "normal_scans": 0,
            "slow_scans": 0,
            "avg_volatility": 0.0,
            "volatility_detections": 0,
            "interval_adjustments": 0,
        }

    async def ensure_markets(self, force: bool = False) -> None:
        now = time.time()
        ttl = self.cfg.market_cache_ttl
        if force or now - self._markets_refreshed_at > ttl or not self._markets_cache:
            self._markets_cache = await fetch_markets(self.cfg)
            self._markets_refreshed_at = now
            log.info(f"Markets refreshed: {len(self._markets_cache)}")

    async def fetch_books_batch(self, token_ids: list[str]) -> dict[str, Any]:
        async with self.client as http:
            books: dict[str, Any] = {}
            for group in chunk(token_ids, self.cfg.book_batch_size):
                payload = {"tokens": group}
                try:
                    resp = await http.post("/books", json=payload)
                    books.update(resp if isinstance(resp, dict) else {})
                except Exception as e:
                    log.error(f"Batch books error: {e}")
            return books

    def _calculate_market_volatility(
        self,
        market_slug: str,
        complement_deviation: float | None,
        max_spread_bps: float | None,
    ) -> float:
        """
        Calculate volatility score for a market based on historical data and current metrics.

        Args:
            market_slug: Market identifier
            complement_deviation: Current complement deviation
            max_spread_bps: Maximum spread in basis points

        Returns:
            Volatility score from 0.0 (stable) to 1.0 (highly volatile)
        """
        volatility_score = 0.0

        # Factor 1: Complement deviation magnitude (40% weight)
        if complement_deviation is not None:
            # Normalize deviation: 0.02 (2%) = medium volatility, 0.05+ = high volatility
            deviation_score = min(1.0, complement_deviation / 0.05) * 0.4
            volatility_score += deviation_score

            # Track historical deviations for trend analysis
            if market_slug not in self.market_history:
                self.market_history[market_slug] = []

            self.market_history[market_slug].append(complement_deviation)
            # Keep only last 20 data points
            if len(self.market_history[market_slug]) > 20:
                self.market_history[market_slug] = self.market_history[market_slug][
                    -20:
                ]

        # Factor 2: Historical deviation variance (30% weight)
        if (
            market_slug in self.market_history
            and len(self.market_history[market_slug]) >= 3
        ):
            history = self.market_history[market_slug]
            mean_deviation = sum(history) / len(history)
            variance = sum((d - mean_deviation) ** 2 for d in history) / len(history)
            # Normalize variance: high variance indicates volatility
            variance_score = (
                min(1.0, variance * 100) * 0.3
            )  # Scale factor for normalization
            volatility_score += variance_score

        # Factor 3: Spread magnitude (20% weight)
        if max_spread_bps is not None:
            # Normalize spread: 500 bps (5%) = medium, 1000+ bps = high volatility
            spread_score = min(1.0, max_spread_bps / 1000) * 0.2
            volatility_score += spread_score

        # Factor 4: Rate of change in recent scans (10% weight)
        if (
            market_slug in self.market_history
            and len(self.market_history[market_slug]) >= 2
            and complement_deviation is not None
        ):
            recent_change = abs(
                self.market_history[market_slug][-1]
                - self.market_history[market_slug][-2]
            )
            change_score = min(1.0, recent_change * 50) * 0.1  # Scale recent changes
            volatility_score += change_score

        # Bound the final score
        volatility_score = max(0.0, min(1.0, volatility_score))

        # Cache the volatility score
        self.market_volatility_cache[market_slug] = volatility_score

        return volatility_score

    async def scan_once(self, top: int = 15) -> list[MarketComposite]:
        # Ensure we have fresh market data cached locally
        await self.ensure_markets()

        # Build mapping of market slugs to their token IDs
        # This handles different API response formats gracefully
        token_map = {}
        for m in self._markets_cache:
            # Extract tokens from various possible field names in API response
            tokens = m.get("token_ids") or m.get("tokens") or []
            # Use market slug as primary key, fallback to question text
            market_key = m.get("slug") or m.get("question", "")
            token_map[market_key] = tokens

        # Flatten all tokens into single list for batch fetching
        all_tokens = [t for tokens in token_map.values() for t in tokens]
        if not all_tokens:
            log.warning("No tokens found in market cache")
            return []

        log.info(f"Scanning {len(all_tokens)} tokens across {len(token_map)} markets.")

        # Fetch order book data for all tokens in batches for efficiency
        book_data = await self.fetch_books_batch(all_tokens)
        log.info(f"Fetched {len(book_data)} books.")

        # Process each market to create composite views
        composites: list[MarketComposite] = []

        for slug, tokens in token_map.items():
            # Build order book entries for each token in this market
            entries: list[BookEntry] = []
            yes_price = None  # Price for YES outcome token
            no_price = None  # Price for NO outcome token

            # Process each token's order book data
            for token_id in tokens:
                raw_book = book_data.get(token_id, {})

                # Extract best bid/ask prices from order book
                # Returns None for both if order book is empty or malformed
                bid, ask = best_bid_ask(raw_book) if raw_book else (None, None)

                # Calculate bid-ask spread in basis points (bps)
                # 100 bps = 1%, used for measuring market liquidity
                spread_bps = calc_spread_bps(bid, ask)

                entries.append(BookEntry(token_id, bid, ask, spread_bps))

            # For binary markets, check complement arbitrage opportunities
            # This only works when we have exactly 2 tokens (YES and NO)
            if len(entries) == 2:
                # Use ask price (what we'd pay to buy) for complement analysis
                # Fall back to bid if ask unavailable
                yes_price = entries[0].ask or entries[0].bid
                no_price = entries[1].ask or entries[1].bid

            # Calculate complement deviation: |sum of prices - 1.0|
            # In efficient markets, YES + NO prices should equal 1.0
            # Deviation indicates arbitrage opportunity
            complement_deviation = None
            if yes_price is not None and no_price is not None:
                price_sum = yes_price + no_price
                complement_deviation = abs(price_sum - 1.0)

            # Calculate volatility and spread metrics for adaptive scanning
            spreads = [
                entry.spread_bps for entry in entries if entry.spread_bps is not None
            ]
            max_spread_bps = max(spreads) if spreads else None
            avg_spread_bps = sum(spreads) / len(spreads) if spreads else None

            # Calculate market volatility score for this market
            volatility_score = self._calculate_market_volatility(
                slug, complement_deviation, max_spread_bps
            )

            current_time = time.time()
            composites.append(
                MarketComposite(
                    slug=slug,
                    tokens=entries,
                    complement_deviation=complement_deviation,
                    max_spread_bps=max_spread_bps,
                    avg_spread_bps=avg_spread_bps,
                    volatility_score=volatility_score,
                    last_updated=current_time,
                )
            )

        log.info(f"Created {len(composites)} composites.")

        # Execute trading strategies on market data
        # Each strategy is given a chance to analyze the composites and generate signals
        for mc in composites:
            # Check each token individually for spread-based opportunities
            # Wide spreads often indicate illiquid markets or pricing inefficiencies
            for entry in mc.tokens:
                for strat in self.strategies:
                    # Only trigger spread strategies that implement on_spread method
                    if hasattr(strat, "on_spread"):
                        try:
                            # Create spread signal with current market data
                            signal = strat.on_spread(
                                SpreadSignal(
                                    market_slug=mc.slug,
                                    token_id=entry.token_id,
                                    bid=entry.bid,  # Best bid price (what buyers offer)
                                    ask=entry.ask,  # Best ask price (what sellers want)
                                    spread_bps=entry.spread_bps,  # Spread in basis points
                                )
                            )
                            # If strategy generates a signal, send it to trading engine
                            if signal:
                                log.debug(f"Spread strategy triggered for {mc.slug}")
                                self.engine.process_signal(signal)
                        except Exception as e:
                            log.error(f"Spread strategy error for {mc.slug}: {e}")

            # Check for complement arbitrage opportunities in binary markets
            # This requires exactly 2 tokens and a calculable deviation
            if mc.complement_deviation is not None:
                for strat in self.strategies:
                    # Only trigger complement strategies that implement on_complement method
                    if hasattr(strat, "on_complement"):
                        try:
                            # Extract YES and NO token prices safely
                            yes_token_id = mc.tokens[0].token_id if mc.tokens else ""
                            no_token_id = (
                                mc.tokens[1].token_id if len(mc.tokens) > 1 else ""
                            )

                            # Use ask prices for arbitrage analysis (cost to enter position)
                            yes_price = (
                                mc.tokens[0].ask or mc.tokens[0].bid
                                if mc.tokens
                                else None
                            )
                            no_price = (
                                mc.tokens[1].ask or mc.tokens[1].bid
                                if len(mc.tokens) > 1
                                else None
                            )

                            # Create complement signal for strategy analysis
                            signals = strat.on_complement(
                                ComplementSignal(
                                    market_slug=mc.slug,
                                    yes_token_id=yes_token_id,
                                    no_token_id=no_token_id,
                                    yes_price=yes_price,
                                    no_price=no_price,
                                    complement_deviation=mc.complement_deviation,
                                )
                            )
                            # Handle both single signal and list of signals for backward compatibility
                            if signals:
                                if isinstance(signals, list):
                                    for signal in signals:
                                        if signal is not None:
                                            self.engine.process_signal(signal)
                                else:
                                    # Backward compatibility for strategies returning single signal
                                    self.engine.process_signal(signals)
                        except Exception as e:
                            log.error(f"Complement strategy error: {e}")

        # Process market making signals if enabled
        if self.market_making_strategy:
            try:
                # Prepare market data for market making strategy
                market_snapshots = []
                for mc in composites:
                    if len(mc.tokens) == 2:  # Binary market
                        yes_token = mc.tokens[0]
                        no_token = mc.tokens[1]

                        # Calculate actual liquidity for this market
                        yes_book_data = book_data.get(yes_token.token_id, {})
                        no_book_data = book_data.get(no_token.token_id, {})

                        # Extract market information for enhanced liquidity calculation
                        # Use MarketComposite data if available, otherwise use defaults
                        market_volume_24h = getattr(mc, "volume_24h", 0.0)
                        market_traders = getattr(mc, "traders", 0)

                        # Calculate liquidity for both tokens with market context
                        yes_liquidity = self.liquidity_calculator.calculate_liquidity_with_market_context(
                            yes_book_data,
                            f"{mc.slug}_YES",
                            volume_24h=market_volume_24h
                            / 2,  # Approximate split between outcomes
                            traders_count=market_traders,
                        )
                        no_liquidity = self.liquidity_calculator.calculate_liquidity_with_market_context(
                            no_book_data,
                            f"{mc.slug}_NO",
                            volume_24h=market_volume_24h
                            / 2,  # Approximate split between outcomes
                            traders_count=market_traders,
                        )
                        total_market_liquidity = yes_liquidity + no_liquidity

                        log.debug(
                            f"Market {mc.slug}: Yes liquidity={yes_liquidity:.2f}, "
                            f"No liquidity={no_liquidity:.2f}, Total={total_market_liquidity:.2f}"
                        )

                        # Create order book data structure expected by strategy
                        market_snapshot = {
                            "market_slug": mc.slug,
                            "liquidity": total_market_liquidity,
                            "outcomes": [
                                {"id": yes_token.token_id, "name": "Yes"},
                                {"id": no_token.token_id, "name": "No"},
                            ],
                            "yes_book": {
                                "bids": (
                                    [{"price": str(yes_token.bid)}]
                                    if yes_token.bid
                                    else []
                                ),
                                "asks": (
                                    [{"price": str(yes_token.ask)}]
                                    if yes_token.ask
                                    else []
                                ),
                            },
                            "no_book": {
                                "bids": (
                                    [{"price": str(no_token.bid)}]
                                    if no_token.bid
                                    else []
                                ),
                                "asks": (
                                    [{"price": str(no_token.ask)}]
                                    if no_token.ask
                                    else []
                                ),
                            },
                        }
                        market_snapshots.append(market_snapshot)

                # Generate market making signals
                mm_signals = self.market_making_strategy.evaluate(
                    {"market_snapshots": market_snapshots}
                )

                # Process each signal through the trading engine
                for signal in mm_signals:
                    try:
                        self.engine.process_signal(signal)
                        log.info(
                            f"Processed market making signal: {signal.market_slug} {signal.side} {signal.price:.3f}"
                        )
                    except Exception as e:
                        log.error(f"Error processing market making signal: {e}")

            except Exception as e:
                log.error(f"Market making strategy error: {e}")

        # Rank by max spread OR complement deviation
        composites.sort(
            key=lambda m: (
                max((e.spread_bps or 0) for e in m.tokens),
                m.complement_deviation or 0,
            ),
            reverse=True,
        )

        # Display signal processing metrics if available
        if hasattr(self.engine, "get_signal_metrics"):
            try:
                signal_metrics = self.engine.get_signal_metrics()
                if signal_metrics.get("signals_received", 0) > 0:
                    log.info(
                        f"Signal processing: {signal_metrics.get('signals_processed', 0)} processed, "
                        f"{signal_metrics.get('signals_expired', 0)} expired, "
                        f"{signal_metrics.get('pending_signals', 0)} pending, "
                        f"avg time: {signal_metrics.get('avg_processing_time', 0):.3f}s"
                    )
            except Exception as e:
                log.debug(f"Could not retrieve signal metrics: {e}")

        # Calculate global volatility score for adaptive scanning
        self._update_global_volatility(composites)

        # Update adaptive scanning statistics
        self.adaptive_stats["total_scans"] += 1

        return composites[:top]

    def _update_global_volatility(self, composites: list[MarketComposite]) -> None:
        """Update global volatility score based on current market conditions."""
        if not composites:
            return

        # Calculate weighted average volatility across all markets
        total_volatility = 0.0
        valid_scores = 0

        for composite in composites:
            if composite.volatility_score is not None:
                total_volatility += composite.volatility_score
                valid_scores += 1

        if valid_scores > 0:
            current_global_volatility = total_volatility / valid_scores

            # Smooth the global volatility using exponential moving average
            alpha = 0.3  # Smoothing factor
            self.global_volatility_score = (
                alpha * current_global_volatility
                + (1 - alpha) * self.global_volatility_score
            )

            # Update scan history for trend analysis
            current_time = time.time()
            self.scan_history.append((current_time, self.global_volatility_score))

            # Keep only last 50 scan results
            if len(self.scan_history) > 50:
                self.scan_history = self.scan_history[-50:]

            # Update running average in stats
            self.adaptive_stats["avg_volatility"] = (
                self.adaptive_stats["avg_volatility"]
                * (self.adaptive_stats["total_scans"] - 1)
                + self.global_volatility_score
            ) / self.adaptive_stats["total_scans"]

            log.debug(
                f"Global volatility updated: {self.global_volatility_score:.3f} "
                f"(from {valid_scores} markets)"
            )

    def _determine_adaptive_interval(self) -> float:
        """
        Determine the next scanning interval based on current market volatility.

        Returns:
            Scanning interval in seconds (5s for high volatility, 30s normal, 60s quiet)
        """
        if not self.adaptive_scanning_enabled:
            return self.base_scan_interval

        volatility = self.global_volatility_score

        # Determine interval based on volatility thresholds
        if volatility >= self.high_volatility_threshold:
            interval = self.fast_scan_interval
            scan_type = "fast"
            self.adaptive_stats["fast_scans"] += 1
        elif volatility <= self.low_volatility_threshold:
            interval = self.slow_scan_interval
            scan_type = "slow"
            self.adaptive_stats["slow_scans"] += 1
        else:
            interval = self.base_scan_interval
            scan_type = "normal"
            self.adaptive_stats["normal_scans"] += 1

        # Check for recent volatility spikes that might warrant faster scanning
        if len(self.scan_history) >= 3:
            recent_volatilities = [v for _, v in self.scan_history[-3:]]
            volatility_trend = recent_volatilities[-1] - recent_volatilities[0]

            # If volatility is increasing rapidly, use faster scanning regardless
            if volatility_trend > 0.2:  # 20% increase in volatility
                interval = min(interval, self.fast_scan_interval)
                scan_type = "fast(trend)"
                self.adaptive_stats["volatility_detections"] += 1

        # Log interval changes
        if hasattr(self, "_last_interval") and self._last_interval != interval:
            self.adaptive_stats["interval_adjustments"] += 1
            log.info(
                f"Adaptive scanning: {scan_type} mode ({interval}s interval) - "
                f"volatility: {volatility:.3f}"
            )

        self._last_interval = interval
        return interval

    async def adaptive_loop(self, top: int = 15) -> None:
        """
        Adaptive scanning loop that adjusts scan frequency based on market volatility.

        High volatility (>0.7): 5-second intervals
        Normal volatility (0.2-0.7): 30-second intervals
        Low volatility (<0.2): 60-second intervals

        Args:
            top: Maximum number of markets to return from each scan
        """
        log.info("Starting adaptive market scanning loop...")
        log.info(
            f"Intervals: Fast={self.fast_scan_interval}s, "
            f"Normal={self.base_scan_interval}s, Slow={self.slow_scan_interval}s"
        )

        # Initialize with normal interval
        self._last_interval = self.base_scan_interval

        while True:
            scan_start = time.perf_counter()

            try:
                # Perform market scan
                composites = await self.scan_once(top)
                self.display(composites)

                # Determine next interval based on current volatility
                next_interval = self._determine_adaptive_interval()

                # Log adaptive scanning statistics periodically
                if self.adaptive_stats["total_scans"] % 20 == 0:
                    self._log_adaptive_stats()

            except Exception as e:
                log.error(f"Adaptive scan error: {e}")
                next_interval = self.base_scan_interval  # Fall back to normal interval

            # Sleep for the calculated interval minus processing time
            scan_duration = time.perf_counter() - scan_start
            sleep_time = max(1.0, next_interval - scan_duration)
            await asyncio.sleep(sleep_time)

    def _log_adaptive_stats(self) -> None:
        """Log adaptive scanning performance statistics."""
        stats = self.adaptive_stats
        total = stats["total_scans"]

        if total > 0:
            log.info(
                f"Adaptive Scanning Stats - "
                f"Total: {total}, Fast: {stats['fast_scans']}, "
                f"Normal: {stats['normal_scans']}, Slow: {stats['slow_scans']}, "
                f"Volatility: {stats['avg_volatility']:.3f}, "
                f"Adjustments: {stats['interval_adjustments']}"
            )

    def get_adaptive_stats(self) -> dict:
        """Get adaptive scanning statistics and configuration."""
        stats = self.adaptive_stats.copy()
        stats.update(
            {
                "adaptive_enabled": self.adaptive_scanning_enabled,
                "current_global_volatility": self.global_volatility_score,
                "fast_interval": self.fast_scan_interval,
                "normal_interval": self.base_scan_interval,
                "slow_interval": self.slow_scan_interval,
                "high_volatility_threshold": self.high_volatility_threshold,
                "low_volatility_threshold": self.low_volatility_threshold,
                "markets_tracked": len(self.market_volatility_cache),
                "scan_history_points": len(self.scan_history),
            }
        )
        return stats

    def display(self, comps: list[MarketComposite]) -> None:
        from .logging_setup import table

        rows = []
        for mc in comps:
            widest = max((e.spread_bps or 0) for e in mc.tokens) if mc.tokens else 0
            dev = mc.complement_deviation
            rows.append(
                [
                    mc.slug[:45],
                    len(mc.tokens),
                    f"{widest:.1f}",
                    f"{dev:.4f}" if dev is not None else "-",
                ]
            )
        table(
            ["Market", "#Toks", "WidestSpread(bps)", "ComplementDev"],
            rows,
            title="Top Markets",
        )

    async def loop(self, interval: int = 30, top: int = 15) -> None:
        while True:
            t0 = time.perf_counter()
            try:
                comps = await self.scan_once(top)
                self.display(comps)
            except Exception as e:
                log.error(f"Loop error: {e}")
            dt = time.perf_counter() - t0
            await asyncio.sleep(max(1, interval - dt))
