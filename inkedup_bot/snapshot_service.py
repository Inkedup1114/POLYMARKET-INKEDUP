from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from .config import BotConfig
from .database import DatabaseManager
from .utils import HTTPClient, best_bid_ask, calc_spread_bps

log = logging.getLogger("snapshot_service")


@dataclass(slots=True)
class MarketSnapshot:
    """Market data snapshot for a specific token."""

    market_slug: str
    token_id: str
    bid: float | None
    ask: float | None
    spread_bps: float | None
    volume_24h: float | None
    liquidity: float | None
    timestamp: float


class SnapshotService:
    """
    Background service for periodic market data capture and storage.

    Collects bid/ask spreads, volume, and liquidity data at regular intervals
    and stores them in the database for historical analysis.
    """

    def __init__(self, cfg: BotConfig, db: DatabaseManager | None = None):
        self.cfg = cfg
        self.db = db or DatabaseManager()
        self.client = HTTPClient(self.cfg.api_base)
        self._running = False
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def initialize(self) -> None:
        """Initialize the snapshot service."""
        await self.db.initialize()
        log.info("SnapshotService initialized")

    async def start(self) -> None:
        """Start the background snapshot collection task."""
        if self._running:
            log.warning("SnapshotService already running")
            return

        await self.initialize()
        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        log.info(
            f"SnapshotService started with {self.cfg.snapshot_interval_seconds}s interval"
        )

    async def stop(self) -> None:
        """Stop the background snapshot collection task."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                log.warning("SnapshotService task did not stop gracefully, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        log.info("SnapshotService stopped")

    async def _run_loop(self) -> None:
        """Main snapshot collection loop."""
        log.info("SnapshotService collection loop started")

        while self._running and not self._stop_event.is_set():
            try:
                await self._collect_snapshots()

                # Clean up old snapshots if configured
                if self.cfg.snapshot_retention_days > 0:
                    await self._cleanup_old_snapshots()

            except Exception as e:
                log.error(f"Error in snapshot collection: {e}", exc_info=True)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.cfg.snapshot_interval_seconds
                )
                break  # Stop event was set
            except TimeoutError:
                continue  # Timeout reached, continue loop

        log.info("SnapshotService collection loop ended")

    async def _collect_snapshots(self) -> None:
        """Collect market data snapshots for all active markets."""
        try:
            # Fetch active markets
            markets = await self._fetch_active_markets()
            log.debug(f"Collecting snapshots for {len(markets)} markets")

            # Collect all token IDs
            all_token_ids = []
            market_token_map = {}

            for market in markets:
                token_ids = market.get("token_ids", [])
                all_token_ids.extend(token_ids)
                for token_id in token_ids:
                    market_token_map[token_id] = market["slug"]

            if not all_token_ids:
                log.warning("No token IDs found for snapshot collection")
                return

            # Fetch order books in batches
            snapshots = []
            batch_size = self.cfg.book_batch_size

            for i in range(0, len(all_token_ids), batch_size):
                batch_tokens = all_token_ids[i : i + batch_size]
                books = await self._fetch_books_batch(batch_tokens)

                # Convert books to snapshots
                for token_id, book_data in books.items():
                    if token_id in market_token_map:
                        snapshot = await self._create_snapshot(
                            market_token_map[token_id], token_id, book_data
                        )
                        if snapshot:
                            snapshots.append(snapshot)

            # Store snapshots in database
            if snapshots:
                await self._store_snapshots(snapshots)
                log.info(f"Collected and stored {len(snapshots)} market snapshots")
            else:
                log.warning("No snapshots collected")

        except Exception as e:
            log.error(f"Failed to collect snapshots: {e}", exc_info=True)

    async def _fetch_active_markets(self) -> list[dict[str, Any]]:
        """Fetch list of active markets to snapshot."""
        try:
            # Use the same logic as Scanner to get markets
            markets = await self.client.get("/markets")

            if not isinstance(markets, list):
                log.error("Invalid markets response format")
                return []

            # Apply filters similar to Scanner
            filtered = []
            for market in markets:
                # Skip if market filters are set and this market doesn't match
                if self.cfg.market_filter and not any(
                    f.lower() in market.get("question", "").lower()
                    for f in self.cfg.market_filter
                ):
                    continue

                # Check minimum volume filter
                volume_24h = market.get("volume24hr", 0)
                if volume_24h < self.cfg.min_volume_24h:
                    continue

                filtered.append(market)

            log.debug(f"Filtered {len(filtered)} markets from {len(markets)} total")
            return filtered

        except Exception as e:
            log.error(f"Failed to fetch active markets: {e}")
            return []

    async def _fetch_books_batch(self, token_ids: list[str]) -> dict[str, Any]:
        """Fetch order books for a batch of token IDs."""
        try:
            if not token_ids:
                return {}

            # Construct the batch request
            params = {"token_ids": ",".join(token_ids)}
            response = await self.client.get("/books", params=params)

            if not isinstance(response, dict):
                log.error("Invalid books response format")
                return {}

            return response

        except Exception as e:
            log.error(f"Failed to fetch books batch: {e}")
            return {}

    async def _create_snapshot(
        self, market_slug: str, token_id: str, book_data: dict[str, Any]
    ) -> MarketSnapshot | None:
        """Create a snapshot from order book data."""
        try:
            bid, ask = best_bid_ask(book_data)
            spread_bps = calc_spread_bps(bid, ask)

            # Extract volume and liquidity if available
            volume_24h = book_data.get("volume24hr")

            # Calculate liquidity as sum of top 5 levels on each side
            liquidity = self._calculate_liquidity(book_data)

            return MarketSnapshot(
                market_slug=market_slug,
                token_id=token_id,
                bid=bid,
                ask=ask,
                spread_bps=spread_bps,
                volume_24h=volume_24h,
                liquidity=liquidity,
                timestamp=time.time(),
            )

        except Exception as e:
            log.error(f"Failed to create snapshot for {token_id}: {e}")
            return None

    def _calculate_liquidity(self, book_data: dict[str, Any]) -> float | None:
        """Calculate total liquidity from order book."""
        try:
            liquidity = 0.0

            # Sum bid side liquidity (top 5 levels)
            bids = book_data.get("bids", [])[:5]
            for bid in bids:
                price = float(bid.get("price", 0))
                size = float(bid.get("size", 0))
                liquidity += price * size

            # Sum ask side liquidity (top 5 levels)
            asks = book_data.get("asks", [])[:5]
            for ask in asks:
                price = float(ask.get("price", 0))
                size = float(ask.get("size", 0))
                liquidity += price * size

            return liquidity if liquidity > 0 else None

        except Exception as e:
            log.error(f"Failed to calculate liquidity: {e}")
            return None

    async def _store_snapshots(self, snapshots: list[MarketSnapshot]) -> None:
        """Store snapshots in the database."""
        try:
            for snapshot in snapshots:
                snapshot_data = {
                    "market_slug": snapshot.market_slug,
                    "token_id": snapshot.token_id,
                    "bid": snapshot.bid,
                    "ask": snapshot.ask,
                    "spread_bps": snapshot.spread_bps,
                    "volume_24h": snapshot.volume_24h,
                    "liquidity": snapshot.liquidity,
                }
                await self.db.insert_market_snapshot(snapshot_data)

        except Exception as e:
            log.error(f"Failed to store snapshots: {e}")

    async def _cleanup_old_snapshots(self) -> None:
        """Remove old snapshots based on retention policy."""
        try:
            cutoff_days = self.cfg.snapshot_retention_days
            if cutoff_days <= 0:
                return

            async with self.db.connection() as db:
                await db.execute(
                    f"""
                    DELETE FROM market_snapshots
                    WHERE snapshot_at < datetime('now', '-{cutoff_days} days')
                    """
                )
                deleted_count = db.total_changes
                await db.commit()

                if deleted_count > 0:
                    log.info(
                        f"Cleaned up {deleted_count} old snapshots (older than {cutoff_days} days)"
                    )

        except Exception as e:
            log.error(f"Failed to cleanup old snapshots: {e}")

    async def get_recent_snapshots(
        self,
        market_slug: str | None = None,
        token_id: str | None = None,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Retrieve recent snapshots for analysis."""
        try:
            conditions = [f"snapshot_at >= datetime('now', '-{hours} hours')"]
            params = []

            if market_slug:
                conditions.append("market_slug = ?")
                params.append(market_slug)

            if token_id:
                conditions.append("token_id = ?")
                params.append(token_id)

            where_clause = " AND ".join(conditions)

            async with self.db.connection() as db:
                cursor = await db.execute(
                    f"""
                    SELECT * FROM market_snapshots
                    WHERE {where_clause}
                    ORDER BY snapshot_at DESC
                    """,
                    params,
                )
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            log.error(f"Failed to get recent snapshots: {e}")
            return []

    async def get_snapshot_stats(
        self, token_id: str, hours: int = 24
    ) -> dict[str, Any] | None:
        """Get statistical summary for a token's recent snapshots."""
        try:
            snapshots = await self.get_recent_snapshots(token_id=token_id, hours=hours)

            if not snapshots:
                return None

            # Calculate statistics
            spreads = [
                s["spread_bps"] for s in snapshots if s["spread_bps"] is not None
            ]
            volumes = [
                s["volume_24h"] for s in snapshots if s["volume_24h"] is not None
            ]

            stats = {
                "token_id": token_id,
                "snapshot_count": len(snapshots),
                "hours_covered": hours,
                "avg_spread_bps": sum(spreads) / len(spreads) if spreads else None,
                "min_spread_bps": min(spreads) if spreads else None,
                "max_spread_bps": max(spreads) if spreads else None,
                "avg_volume_24h": sum(volumes) / len(volumes) if volumes else None,
                "latest_snapshot": snapshots[0] if snapshots else None,
            }

            return stats

        except Exception as e:
            log.error(f"Failed to get snapshot stats for {token_id}: {e}")
            return None
