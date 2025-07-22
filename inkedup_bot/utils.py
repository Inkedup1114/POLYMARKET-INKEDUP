from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from typing import Any

import aiohttp
import orjson

from .config import BotConfig

log = logging.getLogger("utils")
JSONHeaders = {"Accept": "application/json", "Content-Type": "application/json"}


class HTTPClient:
    def __init__(self, base_url: str, timeout: int = 12):
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self.timeout = timeout

    async def __aenter__(self):
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *exc):
        if self._session:
            await self._session.close()

    async def get(self, path: str, params: dict | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        assert self._session
        async with self._session.get(url, params=params, headers=JSONHeaders) as r:
            r.raise_for_status()
            return orjson.loads(await r.read())

    async def post(self, path: str, json: Any) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        assert self._session
        async with self._session.post(
            url, data=orjson.dumps(json), headers=JSONHeaders
        ) as r:
            r.raise_for_status()
            return orjson.loads(await r.read())


async def gather_limited(n: int, coros: Iterable):
    sem = asyncio.Semaphore(n)

    async def _wrap(c):
        async with sem:
            return await c

    return await asyncio.gather(*[_wrap(c) for c in coros], return_exceptions=True)


def best_bid_ask(book: dict) -> tuple[float | None, float | None]:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    bid = float(bids[0]["price"]) if bids else None
    ask = float(asks[0]["price"]) if asks else None
    return bid, ask


def calc_spread_bps(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return (ask - bid) / mid * 10000


def calculate_shares(usd: float, price: float) -> float:
    if price <= 0:
        return 0
    return round(usd / price, 4)


def complement_deviation(
    yes_price: float | None, no_price: float | None
) -> float | None:
    # Deviation of (YES + NO) from 1 (absolute)
    if yes_price is None or no_price is None:
        return None
    return abs((yes_price + no_price) - 1.0)


async def fetch_markets(cfg: BotConfig) -> list[dict]:
    async with HTTPClient(cfg.api_base) as http:
        try:
            data = await http.get("/markets")
        except Exception as e:
            log.error(f"Failed markets fetch: {e}")
            return []
    markets = data if isinstance(data, list) else data.get("markets", [])
    if cfg.market_filter:
        mf = [f.lower() for f in cfg.market_filter]
        markets = [
            m for m in markets if any(f in (m.get("slug") or "").lower() for f in mf)
        ]
    return markets


def chunk(seq: Sequence, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
