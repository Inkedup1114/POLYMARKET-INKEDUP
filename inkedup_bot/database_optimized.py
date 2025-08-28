"""
Optimized database manager with comprehensive indexing and performance monitoring.
Extends the base DatabaseManager with query performance tracking and optimization.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .database import DatabaseManager
from .database_analyzer import DatabaseAnalyzer

log = logging.getLogger("database_optimized")


@dataclass
class QueryMetrics:
    """Metrics for a database query."""

    query_hash: str
    sql_template: str
    execution_count: int = 0
    total_execution_time: float = 0.0
    avg_execution_time: float = 0.0
    min_execution_time: float = float("inf")
    max_execution_time: float = 0.0
    last_executed: datetime | None = None
    error_count: int = 0
    slow_query_count: int = 0  # Count of executions above threshold


@dataclass
class DatabaseStats:
    """Overall database statistics."""

    total_queries: int = 0
    total_execution_time: float = 0.0
    slow_queries: int = 0
    query_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    connection_pool_size: int = 0
    active_connections: int = 0


class OptimizedDatabaseManager(DatabaseManager):
    """
    Enhanced database manager with performance monitoring and optimization features.
    """

    def __init__(
        self,
        db_path: str | Path = "bot_data.db",
        enable_monitoring: bool = True,
        slow_query_threshold: float = 0.1,  # 100ms
        metrics_retention_hours: int = 24,
    ):
        super().__init__(db_path)

        # Performance monitoring settings
        self.enable_monitoring = enable_monitoring
        self.slow_query_threshold = slow_query_threshold
        self.metrics_retention_hours = metrics_retention_hours

        # Query metrics storage
        self.query_metrics: dict[str, QueryMetrics] = {}
        self.recent_queries: deque = deque(maxlen=1000)  # Store recent query details
        self.database_stats = DatabaseStats()

        # Query result cache (simple LRU-style cache)
        self.query_cache: dict[str, tuple[Any, datetime]] = {}
        self.cache_ttl = timedelta(minutes=5)  # 5-minute cache TTL
        self.max_cache_size = 100

        # Initialize database analyzer
        self.analyzer: DatabaseAnalyzer | None = None

        # Lock for thread-safe metrics updates
        self._metrics_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database with optimized indexes."""
        await super().initialize()

        # Create analyzer after database is initialized
        self.analyzer = DatabaseAnalyzer(self)

        # Apply optimized indexes
        await self._create_optimized_indexes()

        # Start background metrics cleanup task
        if self.enable_monitoring:
            asyncio.create_task(self._metrics_cleanup_task())

    async def _create_optimized_indexes(self) -> None:
        """Create additional optimized indexes based on query patterns."""
        optimized_indexes = [
            # High-priority composite indexes for common query patterns
            "CREATE INDEX IF NOT EXISTS idx_orders_status_created_at ON orders(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_orders_token_status ON orders(token_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_orders_market_status ON orders(market_slug, status)",
            "CREATE INDEX IF NOT EXISTS idx_positions_market_outcome ON positions(market_slug, outcome_type)",
            "CREATE INDEX IF NOT EXISTS idx_positions_outcome_updated ON positions(outcome_type, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_trades_token_executed ON trades(token_id, executed_at)",
            "CREATE INDEX IF NOT EXISTS idx_trades_executed_at_desc ON trades(executed_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_market_snapshots_token_snapshot ON market_snapshots(token_id, snapshot_at)",
            "CREATE INDEX IF NOT EXISTS idx_market_snapshots_market_snapshot ON market_snapshots(market_slug, snapshot_at)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_market_updated ON outcome_exposures(market_slug, last_updated)",
            "CREATE INDEX IF NOT EXISTS idx_outcome_exposures_outcome_updated ON outcome_exposures(outcome_id, last_updated)",
            "CREATE INDEX IF NOT EXISTS idx_risk_events_type_occurred ON risk_events(event_type, occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_risk_events_token_occurred ON risk_events(token_id, occurred_at)",
            "CREATE INDEX IF NOT EXISTS idx_exposure_alerts_type_triggered ON exposure_alerts(alert_type, triggered_at)",
            "CREATE INDEX IF NOT EXISTS idx_exposure_alerts_unacknowledged ON exposure_alerts(acknowledged, triggered_at) WHERE acknowledged = FALSE",
            # Partial indexes for performance
            "CREATE INDEX IF NOT EXISTS idx_orders_open_status ON orders(created_at) WHERE status = 'OPEN'",
            "CREATE INDEX IF NOT EXISTS idx_positions_nonzero ON positions(market_slug, notional_value) WHERE ABS(notional_value) > 0",
        ]

        async with self.connection() as db:
            for index_sql in optimized_indexes:
                try:
                    await db.execute(index_sql)
                    log.debug(f"Created optimized index: {index_sql}")
                except Exception as e:
                    log.warning(f"Failed to create index: {e}")

    @asynccontextmanager
    async def monitored_connection(self) -> AsyncGenerator[Any, None]:
        """Connection wrapper with performance monitoring."""
        try:
            async with self.connection() as conn:
                if self.enable_monitoring:
                    # Update connection stats
                    self.database_stats.active_connections += 1

                yield conn

        except Exception:
            if self.enable_monitoring:
                self.database_stats.query_errors += 1
            raise
        finally:
            if self.enable_monitoring:
                self.database_stats.active_connections = max(
                    0, self.database_stats.active_connections - 1
                )

    async def execute_monitored_query(
        self,
        sql: str,
        parameters: tuple = (),
        fetch_all: bool = True,
        cache_key: str | None = None,
    ) -> Any:
        """Execute query with performance monitoring and optional caching."""

        # Check cache first
        if cache_key and self.enable_monitoring:
            cached_result = self._get_cached_result(cache_key)
            if cached_result is not None:
                self.database_stats.cache_hits += 1
                return cached_result
            self.database_stats.cache_misses += 1

        query_hash = self._generate_query_hash(sql)
        start_time = time.perf_counter()

        try:
            async with self.monitored_connection() as conn:
                async with conn.execute(sql, parameters) as cursor:
                    if fetch_all:
                        result = await cursor.fetchall()
                        result = [dict(row) for row in result] if result else []
                    else:
                        result = await cursor.fetchone()
                        result = dict(result) if result else None

                    # Cache result if requested
                    if cache_key and self.enable_monitoring:
                        self._cache_result(cache_key, result)

                    return result

        except Exception as e:
            await self._record_query_error(query_hash, sql, str(e))
            raise
        finally:
            execution_time = time.perf_counter() - start_time
            await self._record_query_metrics(query_hash, sql, execution_time)

    def _get_cached_result(self, cache_key: str) -> Any:
        """Get result from cache if not expired."""
        if cache_key in self.query_cache:
            result, cached_at = self.query_cache[cache_key]
            if datetime.now() - cached_at < self.cache_ttl:
                return result
            else:
                # Remove expired entry
                del self.query_cache[cache_key]
        return None

    def _cache_result(self, cache_key: str, result: Any) -> None:
        """Cache query result with TTL."""
        # Simple cache eviction if at max size
        if len(self.query_cache) >= self.max_cache_size:
            # Remove oldest entry
            oldest_key = min(
                self.query_cache.keys(), key=lambda k: self.query_cache[k][1]
            )
            del self.query_cache[oldest_key]

        self.query_cache[cache_key] = (result, datetime.now())

    def _generate_query_hash(self, sql: str) -> str:
        """Generate hash for SQL query template."""
        # Normalize query by removing parameter placeholders and extra whitespace
        normalized = " ".join(sql.replace("?", "PARAM").split())
        return str(hash(normalized))

    async def _record_query_metrics(
        self, query_hash: str, sql: str, execution_time: float
    ) -> None:
        """Record performance metrics for a query."""
        if not self.enable_monitoring:
            return

        async with self._metrics_lock:
            self.database_stats.total_queries += 1
            self.database_stats.total_execution_time += execution_time

            if execution_time > self.slow_query_threshold:
                self.database_stats.slow_queries += 1

            # Update or create query metrics
            if query_hash in self.query_metrics:
                metrics = self.query_metrics[query_hash]
                metrics.execution_count += 1
                metrics.total_execution_time += execution_time
                metrics.avg_execution_time = (
                    metrics.total_execution_time / metrics.execution_count
                )
                metrics.min_execution_time = min(
                    metrics.min_execution_time, execution_time
                )
                metrics.max_execution_time = max(
                    metrics.max_execution_time, execution_time
                )
                metrics.last_executed = datetime.now()

                if execution_time > self.slow_query_threshold:
                    metrics.slow_query_count += 1
            else:
                self.query_metrics[query_hash] = QueryMetrics(
                    query_hash=query_hash,
                    sql_template=sql,
                    execution_count=1,
                    total_execution_time=execution_time,
                    avg_execution_time=execution_time,
                    min_execution_time=execution_time,
                    max_execution_time=execution_time,
                    last_executed=datetime.now(),
                    slow_query_count=(
                        1 if execution_time > self.slow_query_threshold else 0
                    ),
                )

            # Store recent query details
            self.recent_queries.append(
                {
                    "query_hash": query_hash,
                    "sql": sql[:100] + "..." if len(sql) > 100 else sql,
                    "execution_time": execution_time,
                    "executed_at": datetime.now(),
                    "is_slow": execution_time > self.slow_query_threshold,
                }
            )

    async def _record_query_error(self, query_hash: str, sql: str, error: str) -> None:
        """Record query error metrics."""
        if not self.enable_monitoring:
            return

        async with self._metrics_lock:
            self.database_stats.query_errors += 1

            if query_hash in self.query_metrics:
                self.query_metrics[query_hash].error_count += 1

            log.error(
                f"Database query error - Hash: {query_hash}, SQL: {sql[:100]}..., Error: {error}"
            )

    async def _metrics_cleanup_task(self) -> None:
        """Background task to clean up old metrics data."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                cutoff_time = datetime.now() - timedelta(
                    hours=self.metrics_retention_hours
                )

                async with self._metrics_lock:
                    # Clean up old query metrics
                    to_remove = []
                    for query_hash, metrics in self.query_metrics.items():
                        if (
                            metrics.last_executed
                            and metrics.last_executed < cutoff_time
                        ):
                            to_remove.append(query_hash)

                    for query_hash in to_remove:
                        del self.query_metrics[query_hash]

                    # Clean up old cached results
                    expired_keys = []
                    for cache_key, (_, cached_at) in self.query_cache.items():
                        if datetime.now() - cached_at > self.cache_ttl:
                            expired_keys.append(cache_key)

                    for cache_key in expired_keys:
                        del self.query_cache[cache_key]

                if to_remove or expired_keys:
                    log.info(
                        f"Cleaned up {len(to_remove)} old metrics and {len(expired_keys)} expired cache entries"
                    )

            except Exception as e:
                log.error(f"Error in metrics cleanup task: {e}")

    def get_performance_stats(self) -> dict[str, Any]:
        """Get comprehensive performance statistics."""
        top_slow_queries = sorted(
            self.query_metrics.values(),
            key=lambda x: x.avg_execution_time,
            reverse=True,
        )[:10]

        most_frequent_queries = sorted(
            self.query_metrics.values(), key=lambda x: x.execution_count, reverse=True
        )[:10]

        recent_slow_queries = [
            q
            for q in list(self.recent_queries)[-50:]
            if q["is_slow"]  # Last 50 queries
        ]

        return {
            "database_stats": {
                "total_queries": self.database_stats.total_queries,
                "total_execution_time": round(
                    self.database_stats.total_execution_time, 3
                ),
                "avg_query_time": round(
                    self.database_stats.total_execution_time
                    / max(self.database_stats.total_queries, 1),
                    3,
                ),
                "slow_queries": self.database_stats.slow_queries,
                "query_errors": self.database_stats.query_errors,
                "cache_hits": self.database_stats.cache_hits,
                "cache_misses": self.database_stats.cache_misses,
                "cache_hit_ratio": round(
                    self.database_stats.cache_hits
                    / max(
                        self.database_stats.cache_hits
                        + self.database_stats.cache_misses,
                        1,
                    ),
                    3,
                ),
                "active_connections": self.database_stats.active_connections,
            },
            "top_slow_queries": [
                {
                    "sql": (
                        q.sql_template[:100] + "..."
                        if len(q.sql_template) > 100
                        else q.sql_template
                    ),
                    "avg_time": round(q.avg_execution_time, 3),
                    "max_time": round(q.max_execution_time, 3),
                    "execution_count": q.execution_count,
                    "slow_query_count": q.slow_query_count,
                    "error_count": q.error_count,
                }
                for q in top_slow_queries
            ],
            "most_frequent_queries": [
                {
                    "sql": (
                        q.sql_template[:100] + "..."
                        if len(q.sql_template) > 100
                        else q.sql_template
                    ),
                    "execution_count": q.execution_count,
                    "avg_time": round(q.avg_execution_time, 3),
                    "total_time": round(q.total_execution_time, 3),
                }
                for q in most_frequent_queries
            ],
            "recent_slow_queries": recent_slow_queries[-10:],  # Last 10 slow queries
            "cache_stats": {
                "cached_entries": len(self.query_cache),
                "max_cache_size": self.max_cache_size,
                "cache_ttl_minutes": self.cache_ttl.total_seconds() / 60,
            },
        }

    async def analyze_performance(self) -> str:
        """Generate performance analysis report."""
        if not self.analyzer:
            return "Database analyzer not available"

        # Get index analysis
        index_report = await self.analyzer.generate_optimization_report()

        # Get performance stats
        perf_stats = self.get_performance_stats()

        report = []
        report.append("DATABASE PERFORMANCE ANALYSIS")
        report.append("=" * 40)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Performance summary
        report.append("PERFORMANCE SUMMARY:")
        report.append("-" * 20)
        db_stats = perf_stats["database_stats"]
        report.append(f"Total queries executed: {db_stats['total_queries']}")
        report.append(f"Average query time: {db_stats['avg_query_time']}ms")
        report.append(
            f"Slow queries (>{self.slow_query_threshold*1000}ms): {db_stats['slow_queries']}"
        )
        report.append(f"Query errors: {db_stats['query_errors']}")
        report.append(f"Cache hit ratio: {db_stats['cache_hit_ratio']*100:.1f}%")
        report.append("")

        # Top slow queries
        if perf_stats["top_slow_queries"]:
            report.append("TOP SLOW QUERIES:")
            report.append("-" * 17)
            for i, query in enumerate(perf_stats["top_slow_queries"][:5], 1):
                report.append(f"{i}. {query['sql']}")
                report.append(
                    f"   Avg: {query['avg_time']*1000:.1f}ms, Max: {query['max_time']*1000:.1f}ms"
                )
                report.append(
                    f"   Executions: {query['execution_count']}, Slow: {query['slow_query_count']}"
                )
                report.append("")

        # Index analysis
        report.append(index_report)

        return "\n".join(report)

    # Override frequently used methods with monitoring

    async def get_positions_by_market(self, market_slug: str) -> list[dict[str, Any]]:
        """Get all positions for a specific market with monitoring."""
        cache_key = f"positions_market_{market_slug}"
        return await self.execute_monitored_query(
            "SELECT * FROM positions WHERE market_slug = ?",
            (market_slug,),
            cache_key=cache_key,
        )

    async def get_outcome_exposure(
        self, market_slug: str, outcome_id: str
    ) -> dict[str, Any] | None:
        """Get outcome exposure with monitoring and caching."""
        cache_key = f"outcome_exposure_{market_slug}_{outcome_id}"
        result = await self.execute_monitored_query(
            "SELECT * FROM outcome_exposures WHERE market_slug = ? AND outcome_id = ?",
            (market_slug, outcome_id),
            fetch_all=False,
            cache_key=cache_key,
        )
        return result

    async def get_total_exposure(self) -> float:
        """Calculate total exposure with caching."""
        cache_key = "total_exposure"
        result = await self.execute_monitored_query(
            "SELECT COALESCE(SUM(ABS(notional_value)), 0) FROM positions",
            (),
            fetch_all=False,
            cache_key=cache_key,
        )
        return float(result["COALESCE(SUM(ABS(notional_value)), 0)"]) if result else 0.0


class MonitoredConnection:
    """Wrapper for database connection with query monitoring."""

    def __init__(self, connection: Any, manager: OptimizedDatabaseManager):
        self.connection = connection
        self.manager = manager

    def execute(self, sql: str, parameters: tuple = ()):
        """Execute with monitoring."""
        return self.connection.execute(sql, parameters)

    async def commit(self):
        """Commit transaction."""
        await self.connection.commit()

    async def rollback(self):
        """Rollback transaction."""
        await self.connection.rollback()

    @property
    def row_factory(self):
        """Get row factory from wrapped connection."""
        return self.connection.row_factory

    @row_factory.setter
    def row_factory(self, factory):
        """Set row factory on wrapped connection."""
        self.connection.row_factory = factory

    def __getattr__(self, name):
        """Delegate all other attributes to the wrapped connection."""
        return getattr(self.connection, name)
