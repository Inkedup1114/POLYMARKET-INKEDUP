from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from .config import BotConfig
from .engine import TradingEngine
from .signals import ComplementSignal, SpreadSignal
from .strategies import ComplementArbStrategy, WideSpreadAlertStrategy
from .strategies.market_making import MarketMakingConfig, MarketMakingStrategy
from .utils import HTTPClient, best_bid_ask, calc_spread_bps, chunk, fetch_markets

log = logging.getLogger("scanner")


@dataclass(slots=True)
class BookEntry:
    token_id: str
    bid: float | None
    ask: float | None
    spread_bps: float | None


@dataclass(slots=True)
class MarketComposite:
    slug: str
    tokens: list[BookEntry]
    complement_deviation: float | None = None


class Scanner:
    def __init__(self, cfg: BotConfig | None = None):
        self.cfg = cfg or BotConfig()
        self.client = HTTPClient(self.cfg.api_base)
        self._markets_cache: list[dict] = []
        self._markets_refreshed_at = 0.0
        self.engine = TradingEngine(self.cfg)
        self.strategies = []
        if self.cfg.spread_alert_bps > 0:
            self.strategies.append(WideSpreadAlertStrategy(self.cfg.spread_alert_bps))
        self.strategies.append(
            ComplementArbStrategy()
        )  # default complement deviation monitor

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

    async def ensure_markets(self, force=False):
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

    async def scan_once(self, top: int = 15) -> list[MarketComposite]:
        await self.ensure_markets()
        # Collect token lists
        token_map = {}
        for m in self._markets_cache:
            tokens = m.get("token_ids") or m.get("tokens") or []
            token_map[m.get("slug") or m.get("question", "")] = tokens
        all_tokens = [t for tokens in token_map.values() for t in tokens]
        if not all_tokens:
            return []

        log.info(f"Scanning {len(all_tokens)} tokens across {len(token_map)} markets.")
        book_data = await self.fetch_books_batch(all_tokens)
        log.info(f"Fetched {len(book_data)} books.")
        composites: list[MarketComposite] = []

        for slug, tokens in token_map.items():
            entries: list[BookEntry] = []
            yes_price = None
            no_price = None
            for t in tokens:
                raw = book_data.get(t, {})
                bid, ask = best_bid_ask(raw) if raw else (None, None)
                spread_bps = calc_spread_bps(bid, ask)
                entries.append(BookEntry(t, bid, ask, spread_bps))
            # Attempt complement check if exactly two tokens
            if len(entries) == 2:
                yes_price = entries[0].ask or entries[0].bid
                no_price = entries[1].ask or entries[1].bid
            dev = None
            if yes_price is not None and no_price is not None:
                dev = abs((yes_price + no_price) - 1.0)
            composites.append(MarketComposite(slug, entries, dev))

        log.info(f"Created {len(composites)} composites.")
        # Strategy triggers
        for mc in composites:
            for entry in mc.tokens:
                for strat in self.strategies:
                    if hasattr(strat, "on_spread"):
                        try:
                            signal = strat.on_spread(
                                SpreadSignal(
                                    mc.slug,
                                    entry.token_id,
                                    entry.bid,
                                    entry.ask,
                                    entry.spread_bps,
                                )
                            )
                            if signal:
                                self.engine.process_signal(signal)
                        except Exception as e:
                            log.error(f"Spread strategy error: {e}")
            if mc.complement_deviation is not None:
                for strat in self.strategies:
                    if hasattr(strat, "on_complement"):
                        try:
                            signal = strat.on_complement(
                                ComplementSignal(
                                    mc.slug,
                                    mc.tokens[0].token_id if mc.tokens else "",
                                    mc.tokens[1].token_id if len(mc.tokens) > 1 else "",
                                    (
                                        mc.tokens[0].ask or mc.tokens[0].bid
                                        if mc.tokens
                                        else None
                                    ),
                                    (
                                        mc.tokens[1].ask or mc.tokens[1].bid
                                        if len(mc.tokens) > 1
                                        else None
                                    ),
                                    mc.complement_deviation,
                                )
                            )
                            if signal:
                                self.engine.process_signal(signal)
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

                        # Create order book data structure expected by strategy
                        market_snapshot = {
                            "market_slug": mc.slug,
                            "liquidity": 1000.0,  # TODO: Get actual liquidity data
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
        return composites[:top]

    def display(self, comps: list[MarketComposite]):
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

    async def loop(self, interval: int = 30, top: int = 15):
        while True:
            t0 = time.perf_counter()
            try:
                comps = await self.scan_once(top)
                self.display(comps)
            except Exception as e:
                log.error(f"Loop error: {e}")
            dt = time.perf_counter() - t0
            await asyncio.sleep(max(1, interval - dt))
