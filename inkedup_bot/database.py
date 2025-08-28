from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

from .circuit_breaker import CircuitBreakerConfig
from .enhanced_retry_client import ResilientClientConfig, ResilientRetryClient
from .validation import (
    OrderValidation,
    OutcomeExposureValidation,
    PositionValidation,
    TradeValidation,
    ValidationError,
    safe_database_operation,
    validate_model_data,
)

log = logging.getLogger("database")


class DatabaseManager:
    """
    SQLite database manager for persistent storage of trades, orders, and market data.
    Provides async interface with retry logic and circuit breakers for database operations.
    """

    def __init__(self, db_path: str | Path = "bot_data.db", config=None):
        if aiosqlite is None:
            raise ImportError(
                "aiosqlite is not installed. Please install it with 'pip install aiosqlite'."
            )
        self.db_path = Path(db_path)
        self._conn: Any | None = None  # Use Any to avoid type checking issues
        self._initialized = False
        self._initialization_lock = asyncio.Lock()
        self._is_memory_db = str(db_path) == ":memory:"

        # Initialize retry client for database operations
        self._initialize_retry_client(config)

    def _initialize_retry_client(self, config):
        """Initialize retry client with database-specific configuration."""
        # Database-specific retry configuration - more conservative for data integrity
        circuit_breaker_config = CircuitBreakerConfig(
            failure_threshold=10,  # Higher threshold for DB operations
            recovery_timeout=30.0,  # Shorter recovery time for local DB
            half_open_max_calls=2,
            success_threshold=3,  # Need more successes to trust DB again
            sliding_window_size=50,
            failure_rate_threshold=0.3,  # Lower threshold for DB failures
            call_timeout=60.0,  # Longer timeout for DB operations
        )

        resilient_config = ResilientClientConfig(
            circuit_breaker_enabled=True,
            circuit_breaker_config=circuit_breaker_config,
            default_max_attempts=5,  # More retries for transient DB issues
            default_base_delay=0.5,  # Shorter delays for DB operations
            default_max_delay=30.0,
            exponential_base=1.5,  # Gentler backoff for DB
            jitter_enabled=True,
            jitter_range=0.2,
            call_timeout=60.0,
            total_timeout=300.0,
        )

        self.retry_client = ResilientRetryClient(
            client_name=f"database_manager_{self.db_path.name}", config=resilient_config
        )

        log.info(f"Database retry client initialized for {self.db_path}")

    async def _with_retry(self, operation_name: str, operation_func):
        """Execute database operation with retry logic and circuit breaker protection."""
        return await self.retry_client.call(
            operation_name=f"db_{operation_name}",
            func=operation_func,
            context={"database_path": str(self.db_path), "operation": operation_name},
        )

    async def initialize(self) -> None:
        """Initialize database and create tables if they don't exist."""
        # Use async lock to prevent race conditions during initialization
        async with self._initialization_lock:
            if self._initialized:
                return

            assert aiosqlite is not None

            try:
                # Use retry logic for database initialization
                if self._is_memory_db:
                    await self._with_retry(
                        "initialize_memory_db", self._initialize_memory_db
                    )
                else:
                    await self._with_retry(
                        "initialize_file_db", self._initialize_file_db
                    )

                self._initialized = True
                log.info(f"Database initialized at {self.db_path}")

            except Exception as e:
                log.error(f"Failed to initialize database: {e}")
                # Reset state on failure to allow retry
                self._initialized = False
                if self._conn:
                    try:
                        await self._conn.close()
                    except Exception as e:
                        log.warning(
                            f"Failed to close database connection during initialization failure: {e}"
                        )
                    self._conn = None
                raise

    async def _initialize_memory_db(self) -> None:
        """Initialize in-memory database with persistent connection."""
        self._conn = await aiosqlite.connect(":memory:")
        self._conn.row_factory = aiosqlite.Row

        # Create all tables and indices in a single transaction for atomicity
        async with self._conn.cursor() as cursor:
            await self._create_tables_atomic(cursor)
            await self._conn.commit()

    async def _initialize_file_db(self) -> None:
        """Initialize file-based database with proper directory creation."""
        # Ensure parent directory exists (async-safe approach)
        parent_dir = self.db_path.parent
        if not parent_dir.exists():
            try:
                parent_dir.mkdir(parents=True, exist_ok=True)
            except FileExistsError:
                # Another process created it, that's fine
                pass

        # Create tables in a single transaction
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.cursor() as cursor:
                await self._create_tables_atomic(cursor)
                await db.commit()

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[Any, None]:
        """
        Async context manager for database connections.
        Yields the persistent connection for in-memory DBs, or creates a new
        one for file-based DBs. Thread-safe and race condition resistant.
        """
        # Ensure database is initialized before any connection attempt
        if not self._initialized:
            await self.initialize()

        assert aiosqlite is not None

        # For in-memory databases, use the persistent connection
        if self._conn:
            try:
                yield self._conn
                # Always commit after operations to ensure data persistence
                await self._conn.commit()
            except Exception as e:
                # Rollback on error to maintain consistency
                try:
                    await self._conn.rollback()
                except Exception as rollback_error:
                    log.error(
                        f"Failed to rollback transaction during initialization error: {rollback_error}",
                        exc_info=True,
                    )
                raise e
            return

        # For file-based databases, create new connections per operation
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            try:
                yield db
                # Auto-commit is handled by the context manager
            except Exception as e:
                # The context manager will handle rollback
                raise e

    async def close(self) -> None:
        """Close the persistent database connection if it exists."""
        async with self._initialization_lock:
            if self._conn:
                try:
                    # Commit any pending transactions before closing
                    await self._conn.commit()
                    await self._conn.close()
                except Exception as e:
                    log.warning(f"Error during database close: {e}")
                finally:
                    self._conn = None
                    self._initialized = False
                    log.info("Database connection closed and state reset.")

    async def _create_tables_atomic(self, cursor: Any) -> None:
        """
        Create all required tables and indices atomically in a single transaction.
        This prevents race conditions and ensures database consistency.
        """
        # Define all table creation statements in order of dependency
        table_statements = [
            # Core tables first (no foreign keys)
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, token_id TEXT NOT NULL, market_slug TEXT,
                side TEXT NOT NULL, price REAL NOT NULL, size REAL NOT NULL,
                status TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, filled_at TIMESTAMP,
                notional_value REAL, outcome_type TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS positions (
                token_id TEXT PRIMARY KEY, market_slug TEXT, outcome_type TEXT,
                size REAL NOT NULL, notional_value REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, market_slug TEXT NOT NULL,
                token_id TEXT NOT NULL, bid REAL, ask REAL, spread_bps REAL,
                volume_24h REAL, liquidity REAL,
                snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                token_id TEXT, market_slug TEXT, outcome_type TEXT,
                current_exposure REAL, limit_value REAL, intended_notional REAL,
                description TEXT, occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
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
            """,
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
            """,
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
            """,
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
            """,
            # Tables with foreign keys last
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
                token_id TEXT NOT NULL, market_slug TEXT, side TEXT NOT NULL,
                price REAL NOT NULL, size REAL NOT NULL, notional_value REAL NOT NULL,
                outcome_type TEXT, executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
            """,
        ]

        # Index creation statements (order doesn't matter as much)
        index_statements = [
            "CREATE INDEX IF NOT EXISTS idx_orders_token ON orders(token_id)",
            "CREATE INDEX IF NOT EXISTS idx_orders_market ON orders(market_slug)",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
            "CREATE INDEX IF NOT EXISTS idx_trades_order ON trades(order_id)",
            "CREATE INDEX IF NOT EXISTS idx_trades_token ON trades(token_id)",
            "CREATE INDEX IF NOT EXISTS idx_positions_market ON positions(market_slug)",
            "CREATE INDEX IF NOT EXISTS idx_market_snapshots_token ON market_snapshots(token_id)",
            "CREATE INDEX IF NOT EXISTS idx_risk_events_token ON risk_events(token_id)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_market ON outcome_exposures(market_slug)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_outcome ON outcome_exposures(outcome_id)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_updated ON outcome_exposures(last_updated)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_correlations_outcomes ON outcome_correlations(outcome_a, outcome_b)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_history_market ON outcome_exposure_history(market_slug, outcome_id)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_history_snapshot ON outcome_exposure_history(snapshot_at)",
            "CREATE INDEX IF NOT EXISTS idx_exposure_alerts_type ON exposure_alerts(alert_type, acknowledged)",
        ]

        # Execute all table creations sequentially for dependency resolution
        for statement in table_statements:
            await cursor.execute(statement)

        # Execute all index creations (can be done in any order)
        for statement in index_statements:
            await cursor.execute(statement)

        log.debug("All database tables and indices created successfully")

    # Outcome Exposure Methods
    @safe_database_operation
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
        """Upsert outcome exposure with validation and atomic consistency."""
        # Build exposure data for validation
        exposure_data = {
            "market_slug": market_slug,
            "outcome_id": outcome_id,
            "outcome_name": outcome_name,
            "position_size": position_size,
            "notional_value": notional_value,
            "average_price": average_price,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": realized_pnl,
            "correlation_coefficient": correlation_coefficient,
            "risk_score": risk_score,
        }

        # Validate exposure data
        try:
            validated_exposure = validate_model_data(
                OutcomeExposureValidation, exposure_data
            )
            exp_data = validated_exposure.model_dump()
            # Convert Decimal values to float for SQLite compatibility
            for key in [
                "position_size",
                "notional_value",
                "average_price",
                "current_price",
                "unrealized_pnl",
                "realized_pnl",
                "correlation_coefficient",
                "risk_score",
            ]:
                if key in exp_data and exp_data[key] is not None:
                    exp_data[key] = float(exp_data[key])
        except ValidationError as e:
            log.error(f"Outcome exposure validation failed: {e}")
            raise

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
                    exp_data["market_slug"],
                    exp_data["outcome_id"],
                    exp_data["outcome_name"],
                    exp_data["position_size"],
                    exp_data["notional_value"],
                    exp_data["average_price"],
                    exp_data["current_price"],
                    exp_data["unrealized_pnl"],
                    exp_data["realized_pnl"],
                    exp_data["correlation_coefficient"],
                    exp_data["risk_score"],
                ),
            )

    async def get_outcome_exposure(
        self, market_slug: str, outcome_id: str
    ) -> dict[str, Any] | None:
        """Get outcome exposure by market and outcome ID."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT * FROM outcome_exposures WHERE market_slug = ? AND outcome_id = ?",
                (market_slug, outcome_id),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_outcome_exposures_by_market(
        self, market_slug: str
    ) -> list[dict[str, Any]]:
        """Get all outcome exposures for a market."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT * FROM outcome_exposures WHERE market_slug = ?",
                (market_slug,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_all_outcome_exposures(self) -> list[dict[str, Any]]:
        """Get all outcome exposures."""
        async with self.connection() as db:
            async with db.execute("SELECT * FROM outcome_exposures") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def update_outcome_price(
        self, market_slug: str, outcome_id: str, new_price: float
    ) -> None:
        """Update current price for an outcome exposure."""
        async with self.connection() as db:
            await db.execute(
                """
                UPDATE outcome_exposures
                SET current_price = ?, last_updated = CURRENT_TIMESTAMP
                WHERE market_slug = ? AND outcome_id = ?
                """,
                (new_price, market_slug, outcome_id),
            )

    async def update_outcome_pnl(
        self,
        market_slug: str,
        outcome_id: str,
        unrealized_pnl: float,
        realized_pnl: float,
    ) -> None:
        """Update PNL values for an outcome exposure."""
        async with self.connection() as db:
            await db.execute(
                """
                UPDATE outcome_exposures
                SET unrealized_pnl = ?, realized_pnl = ?, last_updated = CURRENT_TIMESTAMP
                WHERE market_slug = ? AND outcome_id = ?
                """,
                (unrealized_pnl, realized_pnl, market_slug, outcome_id),
            )

    # Basic exposure tracking methods needed by StateManager
    async def get_total_exposure(self) -> float:
        """Calculate total exposure across all open positions."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT COALESCE(SUM(ABS(notional_value)), 0) FROM positions"
            ) as cursor:
                result = await cursor.fetchone()
                return float(result[0]) if result and result[0] is not None else 0.0

    async def get_market_exposure(self, market_slug: str) -> float:
        """Calculate total exposure for a specific market."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT COALESCE(SUM(ABS(notional_value)), 0) FROM positions WHERE market_slug = ?",
                (market_slug,),
            ) as cursor:
                result = await cursor.fetchone()
                return float(result[0]) if result and result[0] is not None else 0.0

    async def get_outcome_exposure(self, outcome_type: str) -> float:
        """Calculate total exposure for a specific outcome type (e.g., 'YES', 'NO')."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT COALESCE(SUM(ABS(notional_value)), 0) FROM positions WHERE outcome_type = ?",
                (outcome_type,),
            ) as cursor:
                result = await cursor.fetchone()
                return float(result[0]) if result and result[0] is not None else 0.0

    async def get_position_notional(self, token_id: str) -> float:
        """Get notional value of a specific position."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT notional_value FROM positions WHERE token_id = ?",
                (token_id,),
            ) as cursor:
                result = await cursor.fetchone()
                return float(result[0]) if result and result[0] is not None else 0.0

    # Position management methods
    @safe_database_operation
    async def insert_order(self, order: dict[str, Any]) -> None:
        """Insert a new order into the database with validation."""
        # Validate order data before insertion
        try:
            validated_order = validate_model_data(OrderValidation, order)
            order_data = validated_order.model_dump()
            # Convert Decimal values to float for SQLite compatibility
            for key in ["price", "size", "notional_value"]:
                if key in order_data and order_data[key] is not None:
                    order_data[key] = float(order_data[key])
        except ValidationError as e:
            log.error(f"Order validation failed: {e}")
            raise

        async with self.connection() as db:
            await db.execute(
                """
                INSERT INTO orders (
                    id, token_id, market_slug, side, price, size, status,
                    notional_value, outcome_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_data.get("id"),
                    order_data.get("token_id"),
                    order_data.get("market_slug"),
                    order_data.get("side"),
                    order_data.get("price"),
                    order_data.get("size"),
                    order_data.get("status", "OPEN"),
                    order_data.get("notional_value", 0.0),
                    order_data.get("outcome_type"),
                ),
            )

    @safe_database_operation
    async def update_order(self, order_id: str, update_data: dict[str, Any]) -> None:
        """Update an existing order with validation."""
        if not update_data:
            return

        # Validate order_id
        if not order_id or not isinstance(order_id, str):
            raise ValidationError("Order ID must be a non-empty string")

        # Build dynamic update query with validation
        set_clauses = []
        params = []

        # Validate each field being updated
        allowed_fields = {"status", "filled_at", "size", "price", "notional_value"}
        for key, value in update_data.items():
            if key in allowed_fields:
                # Basic validation for each field type
                if key == "status" and value not in [
                    "OPEN",
                    "FILLED",
                    "PARTIALLY_FILLED",
                    "CANCELLED",
                    "PENDING",
                    "FAILED",
                ]:
                    raise ValidationError(f"Invalid order status: {value}")
                elif key in ["size", "price", "notional_value"] and (
                    not isinstance(value, (int, float)) or value < 0
                ):
                    raise ValidationError(f"Invalid {key} value: {value}")
                elif (
                    key == "filled_at"
                    and value is not None
                    and not isinstance(value, datetime)
                ):
                    raise ValidationError(f"Invalid filled_at timestamp: {value}")

                set_clauses.append(f"{key} = ?")
                params.append(value)

        if not set_clauses:
            return

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        params.append(order_id)

        async with self.connection() as db:
            await db.execute(
                f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )

    @safe_database_operation
    async def upsert_position(self, position_data: dict[str, Any]) -> None:
        """Insert or update a position with validation."""
        # Validate position data before insertion
        try:
            validated_position = validate_model_data(PositionValidation, position_data)
            pos_data = validated_position.model_dump()
            # Convert Decimal values to float for SQLite compatibility
            for key in ["size", "notional_value"]:
                if key in pos_data and pos_data[key] is not None:
                    pos_data[key] = float(pos_data[key])
        except ValidationError as e:
            log.error(f"Position validation failed: {e}")
            raise

        async with self.connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO positions (
                    token_id, market_slug, outcome_type, size, notional_value
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    pos_data.get("token_id"),
                    pos_data.get("market_slug"),
                    pos_data.get("outcome_type"),
                    pos_data.get("size", 0.0),
                    pos_data.get("notional_value", 0.0),
                ),
            )

    # Enhanced exposure tracking methods
    async def get_positions_by_market(self, market_slug: str) -> list[dict[str, Any]]:
        """Get all positions for a specific market."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT * FROM positions WHERE market_slug = ?",
                (market_slug,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_positions_by_outcome(self, outcome_type: str) -> list[dict[str, Any]]:
        """Get all positions for a specific outcome type."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT * FROM positions WHERE outcome_type = ?",
                (outcome_type,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_all_positions(self) -> list[dict[str, Any]]:
        """Get all current positions."""
        async with self.connection() as db:
            async with db.execute("SELECT * FROM positions") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_market_summary(self, market_slug: str) -> dict[str, Any]:
        """Get comprehensive market exposure summary."""
        async with self.connection() as db:
            # Get overall market exposure
            async with db.execute(
                """
                SELECT 
                    COUNT(*) as position_count,
                    COALESCE(SUM(notional_value), 0) as total_exposure,
                    COALESCE(SUM(ABS(notional_value)), 0) as absolute_exposure,
                    COALESCE(AVG(ABS(notional_value)), 0) as avg_position_size
                FROM positions WHERE market_slug = ?
                """,
                (market_slug,),
            ) as cursor:
                market_row = await cursor.fetchone()

            # Get outcome breakdown
            async with db.execute(
                """
                SELECT 
                    outcome_type,
                    COUNT(*) as count,
                    COALESCE(SUM(notional_value), 0) as exposure,
                    COALESCE(SUM(ABS(notional_value)), 0) as absolute_exposure
                FROM positions 
                WHERE market_slug = ? 
                GROUP BY outcome_type
                """,
                (market_slug,),
            ) as cursor:
                outcome_rows = await cursor.fetchall()

            return {
                "market_slug": market_slug,
                "position_count": market_row[0] if market_row else 0,
                "total_exposure": float(market_row[1]) if market_row else 0.0,
                "absolute_exposure": float(market_row[2]) if market_row else 0.0,
                "avg_position_size": float(market_row[3]) if market_row else 0.0,
                "outcome_breakdown": [
                    {
                        "outcome_type": row[0],
                        "count": row[1],
                        "exposure": float(row[2]),
                        "absolute_exposure": float(row[3]),
                    }
                    for row in outcome_rows
                ],
            }

    async def get_outcome_summary(self, outcome_type: str) -> dict[str, Any]:
        """Get comprehensive outcome exposure summary."""
        async with self.connection() as db:
            # Get overall outcome exposure
            async with db.execute(
                """
                SELECT 
                    COUNT(*) as position_count,
                    COUNT(DISTINCT market_slug) as market_count,
                    COALESCE(SUM(notional_value), 0) as total_exposure,
                    COALESCE(SUM(ABS(notional_value)), 0) as absolute_exposure,
                    COALESCE(AVG(notional_value), 0) as avg_position_size
                FROM positions WHERE outcome_type = ?
                """,
                (outcome_type,),
            ) as cursor:
                outcome_row = await cursor.fetchone()

            # Get market breakdown
            async with db.execute(
                """
                SELECT 
                    market_slug,
                    COUNT(*) as count,
                    COALESCE(SUM(notional_value), 0) as exposure,
                    COALESCE(SUM(ABS(notional_value)), 0) as absolute_exposure
                FROM positions 
                WHERE outcome_type = ? 
                GROUP BY market_slug
                """,
                (outcome_type,),
            ) as cursor:
                market_rows = await cursor.fetchall()

            return {
                "outcome_type": outcome_type,
                "position_count": outcome_row[0] if outcome_row else 0,
                "market_count": outcome_row[1] if outcome_row else 0,
                "total_exposure": float(outcome_row[2]) if outcome_row else 0.0,
                "absolute_exposure": float(outcome_row[3]) if outcome_row else 0.0,
                "avg_position_size": float(outcome_row[4]) if outcome_row else 0.0,
                "market_breakdown": [
                    {
                        "market_slug": row[0],
                        "count": row[1],
                        "exposure": float(row[2]),
                        "absolute_exposure": float(row[3]),
                    }
                    for row in market_rows
                ],
            }

    async def update_position_exposure(
        self,
        token_id: str,
        size_delta: float,
        notional_delta: float,
        current_price: float | None = None,
    ) -> dict[str, Any]:
        """
        Update position exposure and return the updated position data.
        This method handles incremental updates to position size and exposure.
        """
        async with self.connection() as db:
            # Get current position
            async with db.execute(
                "SELECT * FROM positions WHERE token_id = ?", (token_id,)
            ) as cursor:
                current_pos = await cursor.fetchone()

            if current_pos:
                # Update existing position
                new_size = float(current_pos["size"]) + size_delta
                new_notional = float(current_pos["notional_value"]) + notional_delta

                await db.execute(
                    """
                    UPDATE positions 
                    SET size = ?, notional_value = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE token_id = ?
                    """,
                    (new_size, new_notional, token_id),
                )

                return {
                    "token_id": token_id,
                    "market_slug": current_pos["market_slug"],
                    "outcome_type": current_pos["outcome_type"],
                    "old_size": float(current_pos["size"]),
                    "new_size": new_size,
                    "size_delta": size_delta,
                    "old_notional": float(current_pos["notional_value"]),
                    "new_notional": new_notional,
                    "notional_delta": notional_delta,
                }
            else:
                # This shouldn't happen in normal operation, but handle gracefully
                raise ValueError(f"Position not found for token_id: {token_id}")

    @safe_database_operation
    async def record_trade_impact(
        self,
        token_id: str,
        trade_size: float,
        trade_price: float,
        side: str,
        market_slug: str,
        outcome_type: str,
    ) -> dict[str, Any]:
        """
        Record the impact of a trade on position exposure with validation.
        Returns the exposure changes for risk tracking.
        """
        # Validate trade data
        trade_data = {
            "order_id": f"trade_{token_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "token_id": token_id,
            "market_slug": market_slug,
            "side": side,
            "price": trade_price,
            "size": trade_size,
            "notional_value": abs(trade_size * trade_price),
            "outcome_type": outcome_type,
        }

        try:
            validated_trade = validate_model_data(TradeValidation, trade_data)
            trade_validated = validated_trade.model_dump()
            # Convert Decimal values to float for SQLite compatibility
            for key in ["price", "size", "notional_value"]:
                if key in trade_validated and trade_validated[key] is not None:
                    trade_validated[key] = float(trade_validated[key])
        except ValidationError as e:
            log.error(f"Trade validation failed: {e}")
            raise

        notional_value = trade_validated["notional_value"]

        # Adjust sign based on side
        signed_size = trade_size if side.upper() == "BUY" else -trade_size
        signed_notional = notional_value if side.upper() == "BUY" else -notional_value

        async with self.connection() as db:
            # Check if position exists
            async with db.execute(
                "SELECT size, notional_value FROM positions WHERE token_id = ?",
                (token_id,),
            ) as cursor:
                current_pos = await cursor.fetchone()

            if current_pos:
                # Update existing position
                new_size = float(current_pos["size"]) + signed_size
                new_notional = float(current_pos["notional_value"]) + signed_notional

                # Validate the updated position
                updated_position_data = {
                    "token_id": token_id,
                    "market_slug": market_slug,
                    "outcome_type": outcome_type,
                    "size": new_size,
                    "notional_value": new_notional,
                }

                try:
                    validate_model_data(PositionValidation, updated_position_data)
                except ValidationError as e:
                    log.error(f"Updated position validation failed: {e}")
                    raise

                await db.execute(
                    """
                    UPDATE positions 
                    SET size = ?, notional_value = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE token_id = ?
                    """,
                    (new_size, new_notional, token_id),
                )
            else:
                # Create new position with validation
                new_position_data = {
                    "token_id": token_id,
                    "market_slug": market_slug,
                    "outcome_type": outcome_type,
                    "size": signed_size,
                    "notional_value": signed_notional,
                }

                try:
                    validated_position = validate_model_data(
                        PositionValidation, new_position_data
                    )
                    pos_data = validated_position.model_dump()
                    # Convert Decimal values to float for SQLite compatibility
                    for key in ["size", "notional_value"]:
                        if key in pos_data and pos_data[key] is not None:
                            pos_data[key] = float(pos_data[key])
                except ValidationError as e:
                    log.error(f"New position validation failed: {e}")
                    raise

                await db.execute(
                    """
                    INSERT INTO positions (
                        token_id, market_slug, outcome_type, size, notional_value
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pos_data["token_id"],
                        pos_data["market_slug"],
                        pos_data["outcome_type"],
                        pos_data["size"],
                        pos_data["notional_value"],
                    ),
                )

            # Record the trade in trades table
            await db.execute(
                """
                INSERT INTO trades (
                    order_id, token_id, market_slug, side, price, size, 
                    notional_value, outcome_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_validated["order_id"],
                    trade_validated["token_id"],
                    trade_validated["market_slug"],
                    trade_validated["side"],
                    trade_validated["price"],
                    trade_validated["size"],
                    trade_validated["notional_value"],
                    trade_validated["outcome_type"],
                ),
            )

            return {
                "token_id": token_id,
                "market_slug": market_slug,
                "outcome_type": outcome_type,
                "size_delta": signed_size,
                "notional_delta": signed_notional,
                "trade_notional": notional_value,
                "side": side,
                "price": trade_price,
            }
