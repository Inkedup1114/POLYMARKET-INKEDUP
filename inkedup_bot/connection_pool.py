"""
High-performance database connection pooling with health monitoring and graceful degradation.
Resolves the performance bottleneck of creating new connections per operation.

Supports both PostgreSQL (with asyncpg) and SQLite (with aiosqlite) with:
- Advanced connection pooling with health monitoring
- Graceful degradation when pools are exhausted
- Comprehensive statistics and performance metrics
- Automatic recovery from connection failures
- Circuit breaker pattern for failed connections
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import asyncpg
    from asyncpg import Connection as AsyncpgConnection
except ImportError:
    asyncpg = None
    AsyncpgConnection = None

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

log = logging.getLogger("connection_pool")


class PoolState(Enum):
    """Connection pool states for health monitoring."""

    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    CLOSED = "closed"


class DatabaseScheme(Enum):
    """Supported database schemes."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


@dataclass
class HealthCheckResult:
    """Result of a connection pool health check."""

    healthy: bool
    state: PoolState
    response_time_ms: float = 0.0
    error_message: str | None = None
    checked_at: datetime = field(default_factory=datetime.now)
    consecutive_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert health check result to dictionary."""
        return {
            "healthy": self.healthy,
            "state": self.state.value,
            "response_time_ms": round(self.response_time_ms, 2),
            "error_message": self.error_message,
            "checked_at": self.checked_at.isoformat(),
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker pattern."""

    failure_threshold: int = 5  # Number of failures before opening circuit
    recovery_timeout: int = 60  # Seconds to wait before attempting recovery
    success_threshold: int = 3  # Consecutive successes needed to close circuit


class ConnectionPoolStats:
    """Enhanced statistics tracking for connection pools with health monitoring."""

    def __init__(self):
        # Connection statistics
        self.total_connections_created = 0
        self.total_connections_closed = 0
        self.current_connections_in_use = 0
        self.current_idle_connections = 0
        self.peak_connections_in_use = 0

        # Query statistics
        self.total_queries_executed = 0
        self.total_successful_queries = 0
        self.total_failed_queries = 0
        self.total_query_time = 0.0
        self.max_query_time = 0.0
        self.min_query_time = float("inf")
        self.average_acquire_time_ms = 0.0

        # Pool health statistics
        self.pool_full_events = 0
        self.connection_errors = 0
        self.health_check_failures = 0
        self.recovery_attempts = 0
        self.successful_recoveries = 0
        self.circuit_breaker_activations = 0

        # Timestamps
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.last_health_check = datetime.now()

        # Current pool state
        self.current_state = PoolState.INITIALIZING

    def record_query(self, execution_time: float, success: bool = True):
        """Record query execution statistics."""
        self.total_queries_executed += 1
        self.last_activity = datetime.now()

        if success:
            self.total_successful_queries += 1
            self.total_query_time += execution_time
            self.max_query_time = max(self.max_query_time, execution_time)
            self.min_query_time = min(self.min_query_time, execution_time)
        else:
            self.total_failed_queries += 1

    def record_connection_acquired(self, acquire_time_ms: float = 0.0):
        """Record connection acquisition with timing."""
        self.current_connections_in_use += 1
        self.current_idle_connections = max(0, self.current_idle_connections - 1)
        self.peak_connections_in_use = max(
            self.peak_connections_in_use, self.current_connections_in_use
        )
        self.last_activity = datetime.now()

        # Update average acquire time with exponential moving average
        if acquire_time_ms > 0:
            if self.total_queries_executed == 1:
                self.average_acquire_time_ms = acquire_time_ms
            else:
                alpha = 0.1  # Smoothing factor
                self.average_acquire_time_ms = (
                    alpha * acquire_time_ms + (1 - alpha) * self.average_acquire_time_ms
                )

    def record_connection_released(self):
        """Record connection release."""
        self.current_connections_in_use = max(0, self.current_connections_in_use - 1)
        self.current_idle_connections += 1
        self.last_activity = datetime.now()

    def record_connection_created(self):
        """Record new connection creation."""
        self.total_connections_created += 1
        self.current_idle_connections += 1

    def record_connection_closed(self):
        """Record connection closure."""
        self.total_connections_closed += 1
        self.current_idle_connections = max(0, self.current_idle_connections - 1)

    def record_pool_full(self):
        """Record pool exhaustion event."""
        self.pool_full_events += 1
        log.warning("Connection pool is full - consider increasing max_size")

    def record_connection_error(self):
        """Record connection error."""
        self.connection_errors += 1

    def record_health_check_failure(self):
        """Record health check failure."""
        self.health_check_failures += 1
        self.last_health_check = datetime.now()

    def record_recovery_attempt(self):
        """Record recovery attempt."""
        self.recovery_attempts += 1

    def record_successful_recovery(self):
        """Record successful recovery."""
        self.successful_recoveries += 1

    def record_circuit_breaker_activation(self):
        """Record circuit breaker activation."""
        self.circuit_breaker_activations += 1

    def update_state(self, new_state: PoolState):
        """Update current pool state."""
        if self.current_state != new_state:
            log.info(
                f"Pool state changed: {self.current_state.value} -> {new_state.value}"
            )
            self.current_state = new_state

    def get_avg_query_time(self) -> float:
        """Get average query execution time."""
        if self.total_queries_executed == 0:
            return 0.0
        return self.total_query_time / self.total_queries_executed

    def get_success_rate(self) -> float:
        """Get query success rate as percentage."""
        if self.total_queries_executed == 0:
            return 100.0
        return (self.total_successful_queries / self.total_queries_executed) * 100.0

    def get_uptime_hours(self) -> float:
        """Get pool uptime in hours."""
        return (datetime.now() - self.created_at).total_seconds() / 3600

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to comprehensive dictionary for logging/monitoring."""
        return {
            # Connection statistics
            "total_connections_created": self.total_connections_created,
            "total_connections_closed": self.total_connections_closed,
            "current_connections_in_use": self.current_connections_in_use,
            "current_idle_connections": self.current_idle_connections,
            "peak_connections_in_use": self.peak_connections_in_use,
            # Query statistics
            "total_queries_executed": self.total_queries_executed,
            "total_successful_queries": self.total_successful_queries,
            "total_failed_queries": self.total_failed_queries,
            "success_rate_percent": round(self.get_success_rate(), 2),
            "avg_query_time_ms": round(self.get_avg_query_time() * 1000, 2),
            "max_query_time_ms": round(self.max_query_time * 1000, 2),
            "min_query_time_ms": (
                round(self.min_query_time * 1000, 2)
                if self.min_query_time != float("inf")
                else 0
            ),
            "avg_acquire_time_ms": round(self.average_acquire_time_ms, 2),
            # Pool health statistics
            "pool_full_events": self.pool_full_events,
            "connection_errors": self.connection_errors,
            "health_check_failures": self.health_check_failures,
            "recovery_attempts": self.recovery_attempts,
            "successful_recoveries": self.successful_recoveries,
            "circuit_breaker_activations": self.circuit_breaker_activations,
            # Status and timestamps
            "current_state": self.current_state.value,
            "uptime_hours": round(self.get_uptime_hours(), 2),
            "last_activity": self.last_activity.isoformat(),
            "last_health_check": self.last_health_check.isoformat(),
        }


class BaseConnectionPool(ABC):
    """Enhanced abstract base class for connection pools with health monitoring."""

    def __init__(
        self,
        database_url: str,
        pool_size: int = 10,
        min_size: int = 1,
        max_size: int = 20,
        health_check_interval: int = 60,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ):
        self.database_url = database_url
        self.pool_size = pool_size
        self.min_size = min_size
        self.max_size = max_size
        self.health_check_interval = health_check_interval

        # Initialize enhanced statistics and monitoring
        self.stats = ConnectionPoolStats()
        self._pool: Any | None = None
        self._initialized = False
        self._initialization_lock = asyncio.Lock()

        # Circuit breaker for graceful degradation
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._circuit_breaker_open = False
        self._circuit_breaker_opened_at: datetime | None = None
        self._consecutive_failures = 0
        self._consecutive_successes = 0

        # Health monitoring
        self._health_check_task: asyncio.Task | None = None
        self._last_health_check: HealthCheckResult | None = None

        # Graceful degradation
        self._fallback_mode = False
        self._degraded_until: datetime | None = None

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the connection pool."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection pool."""
        pass

    @abstractmethod
    @asynccontextmanager
    async def acquire_connection(self) -> AsyncGenerator[Any, None]:
        """Acquire a connection from the pool."""
        pass

    @abstractmethod
    async def execute(self, query: str, *params: Any) -> Any:
        """Execute a query with a connection from the pool."""
        pass

    @abstractmethod
    async def fetch_one(self, query: str, *params: Any) -> Any | None:
        """Fetch one row with a connection from the pool."""
        pass

    @abstractmethod
    async def fetch_all(self, query: str, *params: Any) -> list[Any]:
        """Fetch all rows with a connection from the pool."""
        pass

    @abstractmethod
    async def _perform_health_check(self) -> HealthCheckResult:
        """Perform database-specific health check."""
        pass

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations."""
        if not self._circuit_breaker_open:
            return True

        # Check if recovery timeout has passed
        if (
            self._circuit_breaker_opened_at
            and datetime.now() - self._circuit_breaker_opened_at
            > timedelta(seconds=self.circuit_breaker_config.recovery_timeout)
        ):
            log.info(
                "Circuit breaker recovery timeout reached, attempting half-open state"
            )
            return True  # Allow one request to test recovery

        return False

    def _record_success(self):
        """Record successful operation for circuit breaker."""
        self._consecutive_failures = 0
        self._consecutive_successes += 1

        # Close circuit breaker if enough successes
        if (
            self._circuit_breaker_open
            and self._consecutive_successes
            >= self.circuit_breaker_config.success_threshold
        ):
            log.info("Circuit breaker closed - sufficient successful operations")
            self._circuit_breaker_open = False
            self._circuit_breaker_opened_at = None
            self.stats.record_successful_recovery()
            self.stats.update_state(PoolState.HEALTHY)

    def _record_failure(self):
        """Record failed operation for circuit breaker."""
        self._consecutive_successes = 0
        self._consecutive_failures += 1

        # Open circuit breaker if threshold reached
        if (
            not self._circuit_breaker_open
            and self._consecutive_failures
            >= self.circuit_breaker_config.failure_threshold
        ):
            log.warning("Circuit breaker opened due to consecutive failures")
            self._circuit_breaker_open = True
            self._circuit_breaker_opened_at = datetime.now()
            self.stats.record_circuit_breaker_activation()
            self.stats.update_state(PoolState.FAILED)

    async def perform_health_check(self) -> HealthCheckResult:
        """Perform health check and update pool state."""
        try:
            result = await self._perform_health_check()
            self._last_health_check = result

            if result.healthy:
                self._record_success()
                if self.stats.current_state in [PoolState.DEGRADED, PoolState.FAILED]:
                    self.stats.update_state(PoolState.HEALTHY)
                    log.info("Pool health restored")
            else:
                self._record_failure()
                self.stats.record_health_check_failure()
                if self.stats.current_state == PoolState.HEALTHY:
                    self.stats.update_state(PoolState.DEGRADED)

            return result

        except Exception as e:
            self._record_failure()
            self.stats.record_health_check_failure()
            self.stats.update_state(PoolState.FAILED)

            result = HealthCheckResult(
                healthy=False,
                state=PoolState.FAILED,
                error_message=str(e),
                consecutive_failures=self._consecutive_failures,
            )
            self._last_health_check = result
            return result

    async def _start_health_monitoring(self):
        """Start background health monitoring task."""
        if self._health_check_task and not self._health_check_task.done():
            return

        async def health_check_loop():
            while True:
                try:
                    await asyncio.sleep(self.health_check_interval)
                    await self.perform_health_check()
                except asyncio.CancelledError:
                    log.info("Health check monitoring stopped")
                    break
                except Exception as e:
                    log.error(f"Error in health check loop: {e}")
                    await asyncio.sleep(30)  # Brief pause before retrying

        self._health_check_task = asyncio.create_task(health_check_loop())
        log.info(f"Started health monitoring (interval: {self.health_check_interval}s)")

    async def get_pool_status(self) -> dict[str, Any]:
        """Get comprehensive pool status and statistics."""
        return {
            "pool_type": self.__class__.__name__,
            "database_url": (
                self.database_url.split("@")[-1]
                if "@" in self.database_url
                else self.database_url
            ),
            "pool_size": self.pool_size,
            "min_size": self.min_size,
            "max_size": self.max_size,
            "initialized": self._initialized,
            "circuit_breaker_open": self._circuit_breaker_open,
            "fallback_mode": self._fallback_mode,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "last_health_check": (
                self._last_health_check.to_dict() if self._last_health_check else None
            ),
            "stats": self.stats.to_dict(),
        }

    async def close(self) -> None:
        """Enhanced close method with health monitoring cleanup."""
        # Stop health monitoring
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        self.stats.update_state(PoolState.CLOSED)
        await self._close_pool_resources()

    @abstractmethod
    async def _close_pool_resources(self) -> None:
        """Close pool-specific resources."""
        pass


class PostgreSQLConnectionPool(BaseConnectionPool):
    """Enhanced PostgreSQL connection pool using asyncpg with health monitoring."""

    def __init__(
        self,
        database_url: str,
        pool_size: int = 10,
        min_size: int = 1,
        max_size: int = 20,
        command_timeout: float = 60.0,
        server_settings: dict[str, str] | None = None,
        health_check_interval: int = 60,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ):
        if asyncpg is None:
            raise ImportError("asyncpg is required for PostgreSQL connection pooling")

        super().__init__(
            database_url,
            pool_size,
            min_size,
            max_size,
            health_check_interval,
            circuit_breaker_config,
        )
        self.command_timeout = command_timeout
        self.server_settings = server_settings or {
            "application_name": "polymarket_inkedup_bot",
            "tcp_keepalives_idle": "300",
            "tcp_keepalives_interval": "30",
            "tcp_keepalives_count": "3",
        }

    async def initialize(self) -> None:
        """Initialize the PostgreSQL connection pool with enhanced monitoring."""
        async with self._initialization_lock:
            if self._initialized:
                return

            try:
                log.info(
                    f"Initializing PostgreSQL connection pool (size: {self.min_size}-{self.max_size})"
                )
                self.stats.update_state(PoolState.INITIALIZING)

                self._pool = await asyncpg.create_pool(
                    dsn=self.database_url,
                    min_size=self.min_size,
                    max_size=self.max_size,
                    command_timeout=self.command_timeout,
                    server_settings=self.server_settings,
                    init=self._connection_init,
                )

                self._initialized = True
                self.stats.total_connections_created = self.min_size
                self.stats.current_idle_connections = self.min_size
                self.stats.update_state(PoolState.HEALTHY)

                # Start health monitoring
                await self._start_health_monitoring()

                log.info("PostgreSQL connection pool initialized successfully")

            except Exception as e:
                log.error(f"Failed to initialize PostgreSQL connection pool: {e}")
                self.stats.record_connection_error()
                self.stats.update_state(PoolState.FAILED)
                raise

    async def _connection_init(self, connection: Any) -> None:
        """Initialize new database connections with optimized settings."""
        await connection.execute("SET application_name = 'inkedup_trading_bot'")
        await connection.execute("SET timezone = 'UTC'")
        await connection.execute("SET statement_timeout = '60s'")
        await connection.execute("SET lock_timeout = '30s'")

    async def _perform_health_check(self) -> HealthCheckResult:
        """Perform PostgreSQL-specific health check."""
        start_time = time.time()

        try:
            if not self._pool:
                raise RuntimeError("Connection pool not initialized")

            # Test with actual connection acquisition and query
            async with self._pool.acquire(timeout=5.0) as conn:
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise RuntimeError("Health check query returned unexpected result")

                # Test with a more complex query to verify functionality
                await conn.execute("SELECT current_timestamp, current_database()")

            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                healthy=True, state=PoolState.HEALTHY, response_time_ms=response_time
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                healthy=False,
                state=PoolState.FAILED,
                response_time_ms=response_time,
                error_message=str(e),
                consecutive_failures=self._consecutive_failures,
            )

    async def _close_pool_resources(self) -> None:
        """Close the PostgreSQL connection pool resources."""
        if self._pool:
            try:
                await self._pool.close()
                self.stats.total_connections_closed += (
                    self.stats.current_idle_connections
                )
                self.stats.current_idle_connections = 0
                log.info("PostgreSQL connection pool closed")
            except Exception as e:
                log.error(f"Error closing PostgreSQL connection pool: {e}")
            finally:
                self._pool = None
                self._initialized = False

    @asynccontextmanager
    async def acquire_connection(self) -> AsyncGenerator[Any, None]:
        """Acquire a connection from the PostgreSQL pool with circuit breaker support."""
        # Check circuit breaker first
        if not self._check_circuit_breaker():
            raise RuntimeError(
                "Circuit breaker is open - PostgreSQL pool is temporarily unavailable"
            )

        if not self._initialized:
            await self.initialize()

        if not self._pool:
            raise RuntimeError("Connection pool is not initialized")

        start_time = time.time()
        success = False

        try:
            async with self._pool.acquire(timeout=10.0) as connection:
                acquire_time = (time.time() - start_time) * 1000
                self.stats.record_connection_acquired(acquire_time)

                yield connection

                success = True
                self._record_success()
                self.stats.record_connection_released()

        except asyncpg.TooManyConnectionsError:
            self.stats.record_pool_full()
            self._record_failure()
            log.warning(
                "PostgreSQL connection pool exhausted - consider increasing max_size"
            )
            raise RuntimeError("Connection pool exhausted")
        except Exception as e:
            self.stats.record_connection_error()
            self._record_failure()
            log.error(f"Error acquiring PostgreSQL connection: {e}")
            raise
        finally:
            execution_time = time.time() - start_time
            self.stats.record_query(execution_time, success)

    async def execute(self, query: str, *params: Any) -> str:
        """Execute a query with a connection from the PostgreSQL pool."""
        async with self.acquire_connection() as conn:
            return await conn.execute(query, *params)

    async def fetch_one(self, query: str, *params: Any) -> Any | None:
        """Fetch one row with a connection from the PostgreSQL pool."""
        async with self.acquire_connection() as conn:
            return await conn.fetchrow(query, *params)

    async def fetch_all(self, query: str, *params: Any) -> list[Any]:
        """Fetch all rows with a connection from the PostgreSQL pool."""
        async with self.acquire_connection() as conn:
            return await conn.fetch(query, *params)


class SQLiteConnectionPool(BaseConnectionPool):
    """Enhanced SQLite connection pool using aiosqlite with health monitoring."""

    def __init__(
        self,
        database_url: str,
        pool_size: int = 5,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 20.0,
        health_check_interval: int = 60,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ):
        if aiosqlite is None:
            raise ImportError("aiosqlite is required for SQLite connection pooling")

        # SQLite has limited write concurrency, so cap the max size
        max_size = min(max_size, 10)
        super().__init__(
            database_url,
            pool_size,
            min_size,
            max_size,
            health_check_interval,
            circuit_breaker_config,
        )
        self.timeout = timeout
        self._connections: asyncio.Queue[Any] = asyncio.Queue()
        self._all_connections: set[Any] = set()
        self._connection_lock = asyncio.Lock()

        # Parse database path from URL
        if database_url == ":memory:":
            self.db_path = ":memory:"
        else:
            parsed = urlparse(database_url)
            if parsed.scheme == "sqlite":
                self.db_path = parsed.path.lstrip("/")
                if parsed.netloc:  # Handle sqlite:///path format
                    self.db_path = "/" + parsed.netloc + parsed.path
            else:
                # Assume it's a direct file path
                self.db_path = database_url

    async def initialize(self) -> None:
        """Initialize the SQLite connection pool with enhanced monitoring."""
        async with self._initialization_lock:
            if self._initialized:
                return

            try:
                log.info(
                    f"Initializing SQLite connection pool (size: {self.min_size}-{self.max_size})"
                )
                self.stats.update_state(PoolState.INITIALIZING)

                # Ensure directory exists for file databases
                if self.db_path != ":memory:":
                    db_path = Path(self.db_path)
                    db_path.parent.mkdir(parents=True, exist_ok=True)

                # Create minimum number of connections
                for _ in range(self.min_size):
                    conn = await self._create_connection()
                    await self._connections.put(conn)

                self._initialized = True
                self.stats.total_connections_created = self.min_size
                self.stats.current_idle_connections = self.min_size
                self.stats.update_state(PoolState.HEALTHY)

                # Start health monitoring
                await self._start_health_monitoring()

                log.info("SQLite connection pool initialized successfully")

            except Exception as e:
                log.error(f"Failed to initialize SQLite connection pool: {e}")
                self.stats.record_connection_error()
                self.stats.update_state(PoolState.FAILED)
                raise

    async def _create_connection(self) -> Any:
        """Create a new SQLite connection."""
        conn = await aiosqlite.connect(
            self.db_path,
            timeout=self.timeout,
            isolation_level=None,  # Enable autocommit mode
        )
        conn.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrency
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=10000")
        await conn.execute("PRAGMA temp_store=MEMORY")

        self._all_connections.add(conn)
        return conn

    async def _perform_health_check(self) -> HealthCheckResult:
        """Perform SQLite-specific health check."""
        start_time = time.time()

        try:
            # Test with actual connection acquisition and query
            async with self.acquire_connection() as conn:
                async with conn.execute("SELECT 1") as cursor:
                    result = await cursor.fetchone()
                    if not result or result[0] != 1:
                        raise RuntimeError(
                            "Health check query returned unexpected result"
                        )

                # Test with a more complex query to verify functionality
                async with conn.execute("PRAGMA database_list") as cursor:
                    await cursor.fetchone()

            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                healthy=True, state=PoolState.HEALTHY, response_time_ms=response_time
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                healthy=False,
                state=PoolState.FAILED,
                response_time_ms=response_time,
                error_message=str(e),
                consecutive_failures=self._consecutive_failures,
            )

    async def _close_pool_resources(self) -> None:
        """Close the SQLite connection pool resources."""
        try:
            # Close all connections
            for conn in self._all_connections:
                try:
                    await conn.close()
                    self.stats.record_connection_closed()
                except Exception as e:
                    log.warning(f"Error closing SQLite connection: {e}")

            self._all_connections.clear()

            # Clear the queue
            while not self._connections.empty():
                try:
                    self._connections.get_nowait()
                except asyncio.QueueEmpty:
                    break

            self.stats.current_idle_connections = 0
            log.info("SQLite connection pool closed")

        except Exception as e:
            log.error(f"Error closing SQLite connection pool: {e}")
        finally:
            self._initialized = False

    @asynccontextmanager
    async def acquire_connection(self) -> AsyncGenerator[Any, None]:
        """Acquire a connection from the SQLite pool."""
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        connection = None

        try:
            # Try to get an existing connection
            try:
                connection = await asyncio.wait_for(
                    self._connections.get(), timeout=1.0
                )
                self.stats.record_connection_acquired()
            except TimeoutError:
                # Create new connection if pool isn't full
                async with self._connection_lock:
                    if len(self._all_connections) < self.max_size:
                        connection = await self._create_connection()
                        self.stats.record_connection_created()
                        self.stats.record_connection_acquired()
                    else:
                        # Wait for available connection
                        self.stats.record_pool_full()
                        connection = await self._connections.get()
                        self.stats.record_connection_acquired()

            yield connection

        except Exception as e:
            self.stats.record_connection_error()
            log.error(f"Error with SQLite connection: {e}")
            raise
        finally:
            if connection:
                # Return connection to pool
                try:
                    await self._connections.put(connection)
                    self.stats.record_connection_released()
                except Exception as e:
                    log.error(f"Error returning SQLite connection to pool: {e}")
                    # Connection may be corrupted, remove it
                    self._all_connections.discard(connection)
                    try:
                        await connection.close()
                    except Exception as close_error:
                        log.warning(
                            f"Failed to close corrupted SQLite connection: {close_error}"
                        )

            execution_time = time.time() - start_time
            self.stats.record_query(execution_time)

    async def execute(self, query: str, *params: Any) -> Any:
        """Execute a query with a connection from the SQLite pool."""
        async with self.acquire_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor

    async def fetch_one(self, query: str, *params: Any) -> Any | None:
        """Fetch one row with a connection from the SQLite pool."""
        async with self.acquire_connection() as conn:
            async with conn.execute(query, params) as cursor:
                return await cursor.fetchone()

    async def fetch_all(self, query: str, *params: Any) -> list[Any]:
        """Fetch all rows with a connection from the SQLite pool."""
        async with self.acquire_connection() as conn:
            async with conn.execute(query, params) as cursor:
                return await cursor.fetchall()


class ConnectionPoolManager:
    """Factory and manager for database connection pools."""

    @staticmethod
    def create_pool(
        database_url: str,
        pool_size: int = 10,
        min_size: int = 1,
        max_size: int = 20,
        **kwargs,
    ) -> BaseConnectionPool:
        """Create appropriate connection pool based on database URL."""
        parsed_url = urlparse(database_url)

        if parsed_url.scheme in ("postgresql", "postgres"):
            return PostgreSQLConnectionPool(
                database_url=database_url,
                pool_size=pool_size,
                min_size=min_size,
                max_size=max_size,
                **kwargs,
            )
        elif (
            parsed_url.scheme == "sqlite"
            or "/" in database_url
            or database_url == ":memory:"
        ):
            return SQLiteConnectionPool(
                database_url=database_url,
                pool_size=pool_size,
                min_size=min_size,
                max_size=max_size,
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported database URL scheme: {parsed_url.scheme}")

    @staticmethod
    async def test_connection_pool(pool: BaseConnectionPool) -> dict[str, Any]:
        """Test connection pool functionality and performance."""
        test_results = {
            "pool_type": pool.__class__.__name__,
            "initialization_success": False,
            "connection_acquisition_success": False,
            "query_execution_success": False,
            "performance_metrics": {},
            "errors": [],
        }

        try:
            # Test initialization
            start_time = time.time()
            await pool.initialize()
            init_time = time.time() - start_time
            test_results["initialization_success"] = True
            test_results["performance_metrics"]["initialization_time_ms"] = (
                init_time * 1000
            )

            # Test connection acquisition
            start_time = time.time()
            async with pool.acquire_connection() as conn:
                acquisition_time = time.time() - start_time
                test_results["connection_acquisition_success"] = True
                test_results["performance_metrics"][
                    "connection_acquisition_time_ms"
                ] = (acquisition_time * 1000)

                # Test query execution
                start_time = time.time()
                if isinstance(pool, PostgreSQLConnectionPool):
                    result = await conn.fetchval("SELECT 1")
                else:  # SQLite
                    async with conn.execute("SELECT 1") as cursor:
                        result = await cursor.fetchone()

                query_time = time.time() - start_time
                test_results["query_execution_success"] = True
                test_results["performance_metrics"]["query_execution_time_ms"] = (
                    query_time * 1000
                )

        except Exception as e:
            test_results["errors"].append(str(e))
            log.error(f"Connection pool test failed: {e}")

        finally:
            try:
                await pool.close()
            except Exception as e:
                test_results["errors"].append(f"Cleanup error: {str(e)}")

        return test_results
