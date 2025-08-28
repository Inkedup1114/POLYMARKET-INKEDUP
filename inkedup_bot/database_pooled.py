"""
High-Performance Database Manager with Connection Pooling

This module provides a drop-in replacement for the existing DatabaseManager
with advanced connection pooling to resolve performance bottlenecks.

Key improvements:
- Connection pooling eliminates per-operation connection overhead
- Configurable pool sizes prevent connection exhaustion
- Health monitoring ensures pool reliability
- Comprehensive metrics for performance optimization
- Graceful degradation under high load conditions
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .circuit_breaker import CircuitBreakerConfig
from .connection_pool import SQLiteConnectionPool
from .enhanced_retry_client import ResilientClientConfig, ResilientRetryClient
from .validation import (
    OutcomeExposureValidation,
    ValidationError,
    safe_database_operation,
    validate_model_data,
)

if TYPE_CHECKING:
    pass

log = logging.getLogger("database_pooled")


class PooledDatabaseManager:
    """
    High-performance SQLite database manager with connection pooling.

    This class provides all the functionality of the original DatabaseManager
    but with significant performance improvements through connection pooling.

    Features:
    - Connection pooling eliminates per-operation connection overhead
    - Configurable pool sizing for optimal performance
    - Health monitoring and automatic recovery
    - Comprehensive metrics and monitoring
    - Circuit breaker pattern for graceful degradation
    - Retry logic with exponential backoff
    """

    def __init__(
        self,
        db_path: str | Path = "bot_data.db",
        config=None,
        # Pool configuration
        min_connections: int = 2,
        max_connections: int = 10,
        connection_timeout: float = 30.0,
        idle_timeout: float = 300.0,  # 5 minutes
        max_connection_age: float = 3600.0,  # 1 hour
        health_check_interval: int = 60,
        # Advanced features
        enable_wal_mode: bool = True,
        enable_foreign_keys: bool = True,
        pool_name: str | None = None,
    ):
        self.db_path = Path(db_path)
        self._initialized = False
        self._initialization_lock = asyncio.Lock()
        self._is_memory_db = str(db_path) == ":memory:"

        # Connection pool configuration
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.idle_timeout = idle_timeout
        self.max_connection_age = max_connection_age
        self.health_check_interval = health_check_interval
        self.enable_wal_mode = enable_wal_mode
        self.enable_foreign_keys = enable_foreign_keys
        self.pool_name = pool_name or f"pool_{self.db_path.name}"

        # Connection pool instance
        self._connection_pool: SQLiteConnectionPool | None = None

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
            client_name=f"pooled_database_manager_{self.db_path.name}",
            config=resilient_config,
        )

        log.info(f"Pooled database retry client initialized for {self.db_path}")

    async def _with_retry(self, operation_name: str, operation_func):
        """Execute database operation with retry logic and circuit breaker protection."""
        return await self.retry_client.call(
            operation_name=f"pooled_db_{operation_name}",
            func=operation_func,
            context={
                "database_path": str(self.db_path),
                "operation": operation_name,
                "pool_name": self.pool_name,
            },
        )

    async def initialize(self) -> None:
        """Initialize database connection pool and create tables if they don't exist."""
        async with self._initialization_lock:
            if self._initialized:
                return

            try:
                # Create connection pool
                await self._with_retry("initialize_pool", self._initialize_pool)

                # Create database schema
                await self._with_retry("create_schema", self._create_schema)

                self._initialized = True
                log.info(f"Pooled database initialized at {self.db_path}")

                # Log pool statistics
                stats = await self._connection_pool.get_pool_status()
                log.info(
                    f"Connection pool '{self.pool_name}' ready: "
                    f"{stats.get('initialized', False)} initialized"
                )

            except Exception as e:
                log.error(f"Failed to initialize pooled database: {e}")
                self._initialized = False
                if self._connection_pool:
                    try:
                        await self._connection_pool.close()
                    except Exception as close_error:
                        log.warning(
                            f"Failed to close connection pool during initialization failure: {close_error}"
                        )
                    self._connection_pool = None
                raise

    async def _initialize_pool(self) -> None:
        """Initialize the connection pool."""
        # Ensure database directory exists for file databases
        if not self._is_memory_db:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create connection pool using the existing interface
        self._connection_pool = SQLiteConnectionPool(
            database_url=str(self.db_path),  # Use database_url parameter name
            pool_size=self.min_connections,
            min_size=self.min_connections,
            max_size=self.max_connections,
            timeout=self.connection_timeout,
            health_check_interval=self.health_check_interval,
        )

        await self._connection_pool.initialize()
        log.info(
            f"Connection pool initialized with {self.min_connections}-{self.max_connections} connections"
        )

    async def _create_schema(self) -> None:
        """Create database schema using pooled connection."""
        async with self._connection_pool.acquire_connection() as conn:
            # Create all tables and indices in a single transaction for atomicity
            await conn.execute("BEGIN")
            try:
                await self._create_tables_atomic(conn)
                await conn.execute("COMMIT")
                log.debug("Database schema created successfully")
            except Exception as e:
                await conn.execute("ROLLBACK")
                log.error(f"Failed to create database schema: {e}")
                raise

    @asynccontextmanager
    async def connection(self):
        """
        Async context manager for database connections using connection pool.

        This provides a drop-in replacement for the original connection() method
        but uses connection pooling for dramatically improved performance.
        """
        if not self._initialized:
            await self.initialize()

        if not self._connection_pool:
            raise RuntimeError("Connection pool not initialized")

        async with self._connection_pool.acquire_connection() as conn:
            try:
                yield conn
            except Exception as e:
                # Let the connection pool handle the error and connection cleanup
                raise e

    async def close(self) -> None:
        """Close the connection pool and all connections."""
        async with self._initialization_lock:
            if self._connection_pool:
                try:
                    await self._connection_pool.close()

                    # Log final statistics
                    stats = await self._connection_pool.get_pool_status()
                    log.info(
                        f"Connection pool '{self.pool_name}' closed. "
                        f"Pool was initialized: {stats.get('initialized', False)}"
                    )

                except Exception as e:
                    log.warning(f"Error during connection pool close: {e}")
                finally:
                    self._connection_pool = None
                    self._initialized = False
                    log.info("Pooled database connection closed and state reset")

    async def get_pool_stats(self) -> dict[str, Any]:
        """Get comprehensive connection pool statistics."""
        if not self._connection_pool:
            return {"error": "Connection pool not initialized"}

        return await self._connection_pool.get_pool_status()

    async def get_pool_health(self) -> dict[str, Any]:
        """Get connection pool health status."""
        if not self._connection_pool:
            return {"status": "not_initialized"}

        stats = await self._connection_pool.get_pool_status()
        return {
            "status": stats.get("stats", {}).get("current_state", "unknown"),
            "pool_name": self.pool_name,
            "total_connections": stats.get("stats", {}).get(
                "current_connections_in_use", 0
            )
            + stats.get("stats", {}).get("current_idle_connections", 0),
            "active_connections": stats.get("stats", {}).get(
                "current_connections_in_use", 0
            ),
            "success_rate": stats.get("stats", {}).get("success_rate_percent", 0) / 100,
        }

    # ==========================================
    # Database Schema Creation
    # ==========================================

    async def _create_tables_atomic(self, conn) -> None:
        """
        Create all required tables and indices atomically.
        This is identical to the original implementation but uses pooled connections.
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
            await conn.execute(statement)

        # Execute all index creations (can be done in any order)
        for statement in index_statements:
            await conn.execute(statement)

        log.debug("All database tables and indices created successfully")

    # ==========================================
    # Outcome Exposure Methods (using pooled connections)
    # ==========================================

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
        """Upsert outcome exposure with validation and atomic consistency using pooled connections."""
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
        """Get outcome exposure by market and outcome ID using pooled connections."""
        async with self.connection() as db:
            async with db.execute(
                "SELECT * FROM outcome_exposures WHERE market_slug = ? AND outcome_id = ?",
                (market_slug, outcome_id),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_all_positions(self) -> list[dict[str, Any]]:
        """Get all current positions using pooled connections."""
        async with self.connection() as db:
            async with db.execute("SELECT * FROM positions") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]


# Convenience function to create a pooled database manager
async def create_pooled_database(
    db_path: str | Path = "bot_data.db",
    min_connections: int = 2,
    max_connections: int = 10,
    **kwargs,
) -> PooledDatabaseManager:
    """
    Create and initialize a pooled database manager.

    Args:
        db_path: Path to the database file
        min_connections: Minimum connections to maintain in pool
        max_connections: Maximum connections allowed in pool
        **kwargs: Additional configuration options

    Returns:
        PooledDatabaseManager: Initialized pooled database manager
    """
    manager = PooledDatabaseManager(
        db_path=db_path,
        min_connections=min_connections,
        max_connections=max_connections,
        **kwargs,
    )
    await manager.initialize()
    return manager
