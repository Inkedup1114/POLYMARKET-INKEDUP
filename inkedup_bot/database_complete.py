from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, List, Dict, Optional

if TYPE_CHECKING:
    import aiosqlite

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

log = logging.getLogger("database")


class DatabaseManager:
    """
    SQLite database manager for persistent storage of trades, orders, and market data.
    Provides async interface for database operations.
    """

    def __init__(self, db_path: str | Path = "bot_data.db"):
        if aiosqlite is None:
            raise ImportError(
                "aiosqlite is not installed. Please install it with 'pip install aiosqlite'."
            )
        self.db_path = Path(db_path)
        self._conn: Any | None = None  # Use Any to avoid type checking issues
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database and create tables if they don't exist."""
        if self._initialized:
            return

        assert aiosqlite is not None

        if str(self.db_path) == ":memory:":
            self._conn = await aiosqlite.connect(":memory:")
            self._conn.row_factory = aiosqlite.Row
            await self._create_tables(self._conn)
            await self._conn.commit()
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                await self._create_tables(db)
                await db.commit()

        self._initialized = True
        log.info(f"Database initialized at {self.db_path}")

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[Any, None]:
        """
        Async context manager for database connections.
        Yields the persistent connection for in-memory DBs, or creates a new
        one for file-based DBs.
        """
        if not self._initialized:
            await self.initialize()

        assert aiosqlite is not None

        if self._conn:
            yield self._conn
            await self._conn.commit()
            return

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    async def close(self) -> None:
        """Close the persistent database connection if it exists."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            log.info("In-memory database connection closed.")

    async def _create_tables(self, db: Any) -> None:
        """Create all required tables."""
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, token_id TEXT NOT NULL, market_slug TEXT,
                side TEXT NOT NULL, price REAL NOT NULL, size REAL NOT NULL,
                status TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, filled_at TIMESTAMP,
                notional_value REAL, outcome_type TEXT
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
                token_id TEXT NOT NULL, market_slug TEXT, side TEXT NOT NULL,
                price REAL NOT NULL, size REAL NOT NULL, notional_value REAL NOT NULL,
                outcome_type TEXT, executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS positions (
                token_id TEXT PRIMARY KEY, market_slug TEXT, outcome_type TEXT,
                size REAL NOT NULL, notional_value REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, market_slug TEXT NOT NULL,
                token_id TEXT NOT NULL, bid REAL, ask REAL, spread_bps REAL,
                volume_24h REAL, liquidity REAL,
                snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                token_id TEXT, market_slug TEXT, outcome_type TEXT,
                current_exposure REAL, limit_value REAL, intended_notional REAL,
                description TEXT, occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS outcome_exposures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_slug TEXT NOT NULL,
                outcome_id TEXT NOT NULL,
                outcome_name TEXT NOT NULL,
                position_size REAL NOT NULL,
                notional_value REAL NOT NULL,
                average_price REAL NOT NULL,
                current_price REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                realized_pnl REAL NOT NULL,
                correlation_coefficient REAL DEFAULT 0.0,
                risk_score REAL DEFAULT 0.0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(market_slug, outcome_id)
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS outcome_correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                outcome_a TEXT NOT NULL,
                outcome_b TEXT NOT NULL,
                correlation REAL NOT NULL,
                covariance REAL NOT NULL,
                last_calculated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(outcome_a, outcome_b)
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS outcome_exposure_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_slug TEXT NOT NULL,
                outcome_id TEXT NOT NULL,
                outcome_name TEXT NOT NULL,
                position_size REAL NOT NULL,
                notional_value REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                risk_score REAL NOT NULL,
                snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS exposure_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                market_slug TEXT,
                outcome_id TEXT,
                threshold_value REAL,
                current_value REAL,
                alert_message TEXT,
                triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged BOOLEAN DEFAULT FALSE
            )
        """
        )
        
        # Create indices for performance
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_market ON outcome_exposures(market_slug)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_outcome ON outcome_exposures(outcome_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_updated ON outcome_exposures(last_updated)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome_correlations_outcomes ON outcome_correlations(outcome_a, outcome_b)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome_history_market ON outcome_exposure_history(market_slug, outcome_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_outcome_history_snapshot ON outcome_exposure_history(snapshot_at)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_exposure_alerts_type ON exposure_alerts(alert_type, acknowledged)"
        )

    # Outcome Exposure Methods
    async def upsert_outcome_exposure(
        self,
        market_slug: str,
        outcome_id: str,
        outcome_name: str,
        position_size: float,
        notional_value: float,
        average_price: float,
        current_price: float,
        unrealized_pnl: float,
        realized_pnl: float,
        correlation_coefficient: float = 0.0,
        risk_score: float = 0.0,
    ) -> None:
        """Upsert outcome exposure with atomic consistency."""
        async with self.connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO outcome_exposures (
                    market_slug, outcome_id, outcome_name, position_size,
                    notional_value, average_price, current_price, unrealized_pnl,
                    realized_pnl, correlation_coefficient, risk_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    market_slug,
                    outcome_id,
                    outcome_name,
                    position_size,
                    notional_value,
                    average_price,
                    current_price,
                    unrealized_pnl,
                    realized_pnl,
                    correlation_coefficient,
                    risk_score,
                ),
            )

    async def get_outcome_exposure(
        self, market_slug: str, outcome_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get outcome exposure by market and outcome ID."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT * FROM outcome_exposures WHERE market_slug = ? AND outcome_id = ?",
                (market_slug, outcome_id),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None