from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Sequence
from typing import Any

import aiohttp
import orjson

from .config import BotConfig
from .rate_limiter import APIRateLimiter, EndpointType

log = logging.getLogger("utils")
JSONHeaders = {"Accept": "application/json", "Content-Type": "application/json"}


class HTTPClient:
    def __init__(
        self,
        base_url: str,
        timeout: int = 12,
        rate_limiter: APIRateLimiter | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self.timeout = timeout
        self.rate_limiter = rate_limiter

    def _get_endpoint_type(self, path: str) -> EndpointType:
        """Determine the endpoint type based on the URL path."""
        path_lower = path.lower()

        if "/auth" in path_lower or "/login" in path_lower or "/token" in path_lower:
            return EndpointType.AUTHENTICATION
        elif "/order" in path_lower:
            return EndpointType.ORDER_MANAGEMENT
        elif "/position" in path_lower or "/balance" in path_lower:
            return EndpointType.POSITION_QUERIES
        elif "/market" in path_lower or "/book" in path_lower or "/price" in path_lower:
            return EndpointType.MARKET_DATA
        else:
            return EndpointType.GENERAL

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

        # Apply rate limiting if configured
        if self.rate_limiter:
            endpoint_type = self._get_endpoint_type(path)
            await self.rate_limiter.acquire(endpoint_type)

        try:
            async with self._session.get(url, params=params, headers=JSONHeaders) as r:
                r.raise_for_status()
                return orjson.loads(await r.read())
        except aiohttp.ClientResponseError as e:
            if e.status == 429 and self.rate_limiter:  # Rate limited
                endpoint_type = self._get_endpoint_type(path)
                await self.rate_limiter.handle_rate_limit_error(endpoint_type)
                # Re-raise the error so caller can handle retry logic
            raise

    async def post(self, path: str, json: Any) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        assert self._session

        # Apply rate limiting if configured
        if self.rate_limiter:
            endpoint_type = self._get_endpoint_type(path)
            await self.rate_limiter.acquire(endpoint_type)

        try:
            async with self._session.post(
                url, data=orjson.dumps(json), headers=JSONHeaders
            ) as r:
                r.raise_for_status()
                return orjson.loads(await r.read())
        except aiohttp.ClientResponseError as e:
            if e.status == 429 and self.rate_limiter:  # Rate limited
                endpoint_type = self._get_endpoint_type(path)
                await self.rate_limiter.handle_rate_limit_error(endpoint_type)
                # Re-raise the error so caller can handle retry logic
            raise


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
    # Create rate limiter if rate limiting is enabled
    rate_limiter = None
    if cfg.rate_limiting.enabled:
        from .rate_limiter import APIRateLimiter, EndpointType

        rate_limiter = APIRateLimiter(cfg.rate_limiting.default_config)

        # Configure endpoint-specific rate limits
        for endpoint_type, config in cfg.rate_limiting.endpoint_configs.items():
            rate_limiter.configure_endpoint(endpoint_type, config)

    async with HTTPClient(str(cfg.api_base), rate_limiter=rate_limiter) as http:
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
