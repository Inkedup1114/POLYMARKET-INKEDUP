"""
Database Performance Metrics Tracking

Comprehensive database performance monitoring with query timing, connection pool metrics,
transaction analysis, and database health tracking.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any

from .performance_metrics import ComponentType, MetricType, PerformanceMetricsTracker

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Database query types for categorized performance tracking"""

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    CREATE = "create"
    DROP = "drop"
    BEGIN = "begin"
    COMMIT = "commit"
    ROLLBACK = "rollback"
    UNKNOWN = "unknown"


class ConnectionPoolStatus(Enum):
    """Connection pool status for health monitoring"""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


@dataclass
class DatabaseQueryMetric:
    """Individual database query performance metric"""

    query_id: str
    query_type: QueryType
    table_name: str | None
    execution_time_ms: float
    connection_acquire_time_ms: float
    rows_affected: int | None
    success: bool
    error_message: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    connection_pool_id: str | None = None
    transaction_id: str | None = None


@dataclass
class ConnectionPoolMetrics:
    """Connection pool performance and health metrics"""

    pool_id: str
    total_connections: int
    active_connections: int
    idle_connections: int
    waiting_requests: int
    avg_connection_age_seconds: float
    total_queries: int
    failed_queries: int
    avg_query_time_ms: float
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class TransactionMetrics:
    """Database transaction performance tracking"""

    transaction_id: str
    start_time: datetime
    end_time: datetime | None
    queries_count: int
    total_execution_time_ms: float
    commit_time_ms: float | None
    rollback_time_ms: float | None
    success: bool
    isolation_level: str | None = None


class DatabasePerformanceTracker:
    """
    Comprehensive database performance tracking system

    Tracks query performance, connection pool metrics, transaction timing,
    and provides database health assessment.
    """

    def __init__(self, retention_seconds: int = 3600):
        self.retention_seconds = retention_seconds
        self.lock = threading.RLock()

        # Core metrics tracking
        self.performance_tracker = PerformanceMetricsTracker(retention_seconds)

        # Database-specific metrics
        self.query_metrics: deque = deque(maxlen=10000)
        self.connection_pools: dict[str, ConnectionPoolMetrics] = {}
        self.active_transactions: dict[str, TransactionMetrics] = {}
        self.completed_transactions: deque = deque(maxlen=1000)

        # Query statistics by type
        self.query_stats_by_type: dict[QueryType, dict[str, Any]] = defaultdict(
            lambda: {
                "count": 0,
                "total_time_ms": 0.0,
                "min_time_ms": float("inf"),
                "max_time_ms": 0.0,
                "error_count": 0,
                "last_execution": None,
            }
        )

        # Table-specific statistics
        self.table_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "query_count": 0,
                "total_time_ms": 0.0,
                "select_count": 0,
                "insert_count": 0,
                "update_count": 0,
                "delete_count": 0,
                "error_count": 0,
                "avg_rows_affected": 0.0,
            }
        )

        # Performance thresholds
        self.slow_query_threshold_ms = 100.0
        self.critical_query_threshold_ms = 1000.0
        self.connection_pool_warning_threshold = 0.8  # 80% utilization

        logger.info("Database performance tracker initialized")

    def _classify_query(self, query: str) -> tuple[QueryType, str | None]:
        """Classify query type and extract table name"""
        query_lower = query.lower().strip()

        # Query type classification
        if query_lower.startswith("select"):
            query_type = QueryType.SELECT
        elif query_lower.startswith("insert"):
            query_type = QueryType.INSERT
        elif query_lower.startswith("update"):
            query_type = QueryType.UPDATE
        elif query_lower.startswith("delete"):
            query_type = QueryType.DELETE
        elif query_lower.startswith("create"):
            query_type = QueryType.CREATE
        elif query_lower.startswith("drop"):
            query_type = QueryType.DROP
        elif query_lower.startswith("begin"):
            query_type = QueryType.BEGIN
        elif query_lower.startswith("commit"):
            query_type = QueryType.COMMIT
        elif query_lower.startswith("rollback"):
            query_type = QueryType.ROLLBACK
        else:
            query_type = QueryType.UNKNOWN

        # Table name extraction (simplified)
        table_name = None
        try:
            if query_type in [
                QueryType.SELECT,
                QueryType.INSERT,
                QueryType.UPDATE,
                QueryType.DELETE,
            ]:
                words = query_lower.split()
                if "from" in words:
                    table_index = words.index("from") + 1
                    if table_index < len(words):
                        table_name = words[table_index].strip('`"[]')
                elif "into" in words:
                    table_index = words.index("into") + 1
                    if table_index < len(words):
                        table_name = words[table_index].strip('`"[]')
                elif query_type == QueryType.UPDATE and len(words) > 1:
                    table_name = words[1].strip('`"[]')
        except (ValueError, IndexError):
            pass

        return query_type, table_name

    @contextmanager
    def track_query(
        self,
        query: str,
        connection_pool_id: str | None = None,
        transaction_id: str | None = None,
    ):
        """Context manager for tracking database query performance"""
        query_id = f"query_{int(time.time() * 1000000)}"
        query_type, table_name = self._classify_query(query)

        connection_acquire_start = time.perf_counter()
        connection_acquire_time_ms = 0.0
        execution_start = 0.0
        execution_time_ms = 0.0
        rows_affected = None
        success = False
        error_message = None

        try:
            # Simulate connection acquisition time
            yield {
                "query_id": query_id,
                "connection_acquired": lambda: self._mark_connection_acquired(
                    connection_acquire_start, query_id
                ),
            }

            # Mark execution start
            execution_start = time.perf_counter()
            connection_acquire_time_ms = (
                execution_start - connection_acquire_start
            ) * 1000

        except Exception as e:
            error_message = str(e)
            logger.error(f"Database query failed: {query_id}: {error_message}")
            raise

        finally:
            # Calculate execution time
            if execution_start > 0:
                execution_time_ms = (time.perf_counter() - execution_start) * 1000
            else:
                execution_time_ms = (
                    time.perf_counter() - connection_acquire_start
                ) * 1000
                connection_acquire_time_ms = 0.0

            success = error_message is None

            # Record the query metric
            self._record_query_metric(
                query_id,
                query_type,
                table_name,
                execution_time_ms,
                connection_acquire_time_ms,
                rows_affected,
                success,
                error_message,
                connection_pool_id,
                transaction_id,
            )

    def _mark_connection_acquired(self, start_time: float, query_id: str):
        """Mark that database connection has been acquired"""
        acquire_time_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(f"Connection acquired for {query_id} in {acquire_time_ms:.2f}ms")

    def _record_query_metric(
        self,
        query_id: str,
        query_type: QueryType,
        table_name: str | None,
        execution_time_ms: float,
        connection_acquire_time_ms: float,
        rows_affected: int | None,
        success: bool,
        error_message: str | None,
        connection_pool_id: str | None,
        transaction_id: str | None,
    ):
        """Record individual query performance metric"""

        with self.lock:
            # Create query metric
            metric = DatabaseQueryMetric(
                query_id=query_id,
                query_type=query_type,
                table_name=table_name,
                execution_time_ms=execution_time_ms,
                connection_acquire_time_ms=connection_acquire_time_ms,
                rows_affected=rows_affected,
                success=success,
                error_message=error_message,
                connection_pool_id=connection_pool_id,
                transaction_id=transaction_id,
            )

            self.query_metrics.append(metric)

            # Update query type statistics
            type_stats = self.query_stats_by_type[query_type]
            type_stats["count"] += 1
            type_stats["total_time_ms"] += execution_time_ms
            type_stats["min_time_ms"] = min(
                type_stats["min_time_ms"], execution_time_ms
            )
            type_stats["max_time_ms"] = max(
                type_stats["max_time_ms"], execution_time_ms
            )
            type_stats["last_execution"] = datetime.now()

            if not success:
                type_stats["error_count"] += 1

            # Update table statistics
            if table_name:
                table_stat = self.table_stats[table_name]
                table_stat["query_count"] += 1
                table_stat["total_time_ms"] += execution_time_ms
                table_stat[f"{query_type.value}_count"] += 1

                if not success:
                    table_stat["error_count"] += 1

                if rows_affected is not None:
                    current_avg = table_stat["avg_rows_affected"]
                    count = table_stat["query_count"]
                    table_stat["avg_rows_affected"] = (
                        current_avg * (count - 1) + rows_affected
                    ) / count

            # Record in performance tracker
            self.performance_tracker.record_metric(
                ComponentType.DATABASE,
                MetricType.LATENCY,
                f"query_{query_type.value}",
                execution_time_ms,
            )

            # Check for slow queries
            if execution_time_ms > self.slow_query_threshold_ms:
                severity = (
                    "critical"
                    if execution_time_ms > self.critical_query_threshold_ms
                    else "warning"
                )
                logger.warning(
                    f"Slow database query detected [{severity}]: "
                    f"{query_id} ({query_type.value}) took {execution_time_ms:.2f}ms"
                )

    def update_connection_pool_metrics(
        self,
        pool_id: str,
        total_connections: int,
        active_connections: int,
        idle_connections: int,
        waiting_requests: int,
        avg_connection_age_seconds: float,
        total_queries: int,
        failed_queries: int,
        avg_query_time_ms: float,
    ):
        """Update connection pool performance metrics"""

        with self.lock:
            self.connection_pools[pool_id] = ConnectionPoolMetrics(
                pool_id=pool_id,
                total_connections=total_connections,
                active_connections=active_connections,
                idle_connections=idle_connections,
                waiting_requests=waiting_requests,
                avg_connection_age_seconds=avg_connection_age_seconds,
                total_queries=total_queries,
                failed_queries=failed_queries,
                avg_query_time_ms=avg_query_time_ms,
            )

            # Calculate utilization
            utilization = (
                active_connections / total_connections if total_connections > 0 else 0
            )

            # Record pool metrics
            self.performance_tracker.record_metric(
                ComponentType.DATABASE,
                MetricType.GAUGE,
                f"connection_pool_{pool_id}_utilization",
                utilization * 100,
            )

            self.performance_tracker.record_metric(
                ComponentType.DATABASE,
                MetricType.GAUGE,
                f"connection_pool_{pool_id}_waiting_requests",
                waiting_requests,
            )

            # Check for pool health issues
            if utilization > self.connection_pool_warning_threshold:
                logger.warning(
                    f"Connection pool {pool_id} utilization high: "
                    f"{utilization:.1%} ({active_connections}/{total_connections})"
                )

            if waiting_requests > 0:
                logger.warning(
                    f"Connection pool {pool_id} has {waiting_requests} waiting requests"
                )

    @contextmanager
    def track_transaction(
        self, transaction_id: str, isolation_level: str | None = None
    ):
        """Context manager for tracking database transaction performance"""

        start_time = datetime.now()
        queries_count = 0
        success = False
        commit_time_ms = None
        rollback_time_ms = None

        # Initialize transaction tracking
        with self.lock:
            self.active_transactions[transaction_id] = TransactionMetrics(
                transaction_id=transaction_id,
                start_time=start_time,
                end_time=None,
                queries_count=0,
                total_execution_time_ms=0.0,
                commit_time_ms=None,
                rollback_time_ms=None,
                success=False,
                isolation_level=isolation_level,
            )

        try:
            yield {
                "transaction_id": transaction_id,
                "record_commit": lambda ms: self._record_commit_time(
                    transaction_id, ms
                ),
                "record_rollback": lambda ms: self._record_rollback_time(
                    transaction_id, ms
                ),
                "increment_queries": lambda: self._increment_transaction_queries(
                    transaction_id
                ),
            }
            success = True

        except Exception as e:
            logger.error(f"Transaction {transaction_id} failed: {e}")
            raise

        finally:
            end_time = datetime.now()
            total_time_ms = (end_time - start_time).total_seconds() * 1000

            with self.lock:
                if transaction_id in self.active_transactions:
                    transaction_metric = self.active_transactions[transaction_id]
                    transaction_metric.end_time = end_time
                    transaction_metric.total_execution_time_ms = total_time_ms
                    transaction_metric.success = success

                    # Move to completed transactions
                    self.completed_transactions.append(transaction_metric)
                    del self.active_transactions[transaction_id]

                    # Record transaction metrics
                    self.performance_tracker.record_metric(
                        ComponentType.DATABASE,
                        MetricType.LATENCY,
                        "transaction_duration",
                        total_time_ms,
                    )

                    if commit_time_ms:
                        self.performance_tracker.record_metric(
                            ComponentType.DATABASE,
                            MetricType.LATENCY,
                            "transaction_commit",
                            commit_time_ms,
                        )

    def _record_commit_time(self, transaction_id: str, commit_time_ms: float):
        """Record transaction commit time"""
        with self.lock:
            if transaction_id in self.active_transactions:
                self.active_transactions[transaction_id].commit_time_ms = commit_time_ms

    def _record_rollback_time(self, transaction_id: str, rollback_time_ms: float):
        """Record transaction rollback time"""
        with self.lock:
            if transaction_id in self.active_transactions:
                self.active_transactions[transaction_id].rollback_time_ms = (
                    rollback_time_ms
                )

    def _increment_transaction_queries(self, transaction_id: str):
        """Increment query count for transaction"""
        with self.lock:
            if transaction_id in self.active_transactions:
                self.active_transactions[transaction_id].queries_count += 1

    def get_query_performance_stats(self, minutes: int = 60) -> dict[str, Any]:
        """Get comprehensive query performance statistics"""

        cutoff_time = datetime.now().timestamp() - (minutes * 60)

        with self.lock:
            recent_queries = [
                q for q in self.query_metrics if q.timestamp.timestamp() > cutoff_time
            ]

            if not recent_queries:
                return {"total_queries": 0, "time_range_minutes": minutes}

            # Calculate statistics
            total_queries = len(recent_queries)
            successful_queries = sum(1 for q in recent_queries if q.success)
            failed_queries = total_queries - successful_queries

            execution_times = [q.execution_time_ms for q in recent_queries]
            connection_acquire_times = [
                q.connection_acquire_time_ms for q in recent_queries
            ]

            # Query type breakdown
            type_breakdown = defaultdict(int)
            for query in recent_queries:
                type_breakdown[query.query_type.value] += 1

            # Table breakdown
            table_breakdown = defaultdict(int)
            for query in recent_queries:
                if query.table_name:
                    table_breakdown[query.table_name] += 1

            return {
                "total_queries": total_queries,
                "successful_queries": successful_queries,
                "failed_queries": failed_queries,
                "success_rate": (
                    successful_queries / total_queries if total_queries > 0 else 0
                ),
                "time_range_minutes": minutes,
                "execution_time_stats": {
                    "min_ms": min(execution_times) if execution_times else 0,
                    "max_ms": max(execution_times) if execution_times else 0,
                    "avg_ms": (
                        sum(execution_times) / len(execution_times)
                        if execution_times
                        else 0
                    ),
                    "total_ms": sum(execution_times),
                },
                "connection_acquire_stats": {
                    "min_ms": (
                        min(connection_acquire_times) if connection_acquire_times else 0
                    ),
                    "max_ms": (
                        max(connection_acquire_times) if connection_acquire_times else 0
                    ),
                    "avg_ms": (
                        sum(connection_acquire_times) / len(connection_acquire_times)
                        if connection_acquire_times
                        else 0
                    ),
                },
                "query_type_breakdown": dict(type_breakdown),
                "table_breakdown": dict(table_breakdown),
                "slow_queries": len(
                    [
                        q
                        for q in recent_queries
                        if q.execution_time_ms > self.slow_query_threshold_ms
                    ]
                ),
                "critical_queries": len(
                    [
                        q
                        for q in recent_queries
                        if q.execution_time_ms > self.critical_query_threshold_ms
                    ]
                ),
            }

    def get_connection_pool_health(self) -> dict[str, Any]:
        """Get connection pool health assessment"""

        with self.lock:
            pool_health = {}

            for pool_id, metrics in self.connection_pools.items():
                utilization = (
                    metrics.active_connections / metrics.total_connections
                    if metrics.total_connections > 0
                    else 0
                )

                error_rate = (
                    metrics.failed_queries / metrics.total_queries
                    if metrics.total_queries > 0
                    else 0
                )

                # Determine health status
                if (
                    utilization > 0.9
                    or metrics.waiting_requests > 10
                    or error_rate > 0.1
                ):
                    status = ConnectionPoolStatus.CRITICAL
                elif (
                    utilization > 0.8
                    or metrics.waiting_requests > 5
                    or error_rate > 0.05
                ):
                    status = ConnectionPoolStatus.WARNING
                elif metrics.total_connections > 0:
                    status = ConnectionPoolStatus.HEALTHY
                else:
                    status = ConnectionPoolStatus.UNAVAILABLE

                pool_health[pool_id] = {
                    "status": status.value,
                    "utilization": utilization,
                    "active_connections": metrics.active_connections,
                    "total_connections": metrics.total_connections,
                    "waiting_requests": metrics.waiting_requests,
                    "error_rate": error_rate,
                    "avg_query_time_ms": metrics.avg_query_time_ms,
                    "last_updated": metrics.last_updated.isoformat(),
                }

            return pool_health

    def get_database_health_summary(self) -> dict[str, Any]:
        """Get comprehensive database health summary"""

        query_stats = self.get_query_performance_stats(60)
        pool_health = self.get_connection_pool_health()

        # Overall health assessment
        overall_health = "healthy"
        issues = []

        # Check query performance
        if query_stats.get("success_rate", 1.0) < 0.95:
            overall_health = "warning"
            issues.append(
                f"Query success rate below 95%: {query_stats['success_rate']:.1%}"
            )

        if (
            query_stats.get("slow_queries", 0)
            > query_stats.get("total_queries", 1) * 0.1
        ):
            overall_health = "warning"
            issues.append(
                f"High slow query rate: {query_stats['slow_queries']} slow queries"
            )

        if query_stats.get("critical_queries", 0) > 0:
            overall_health = "critical"
            issues.append(
                f"Critical slow queries detected: {query_stats['critical_queries']}"
            )

        # Check connection pool health
        critical_pools = [
            pool_id
            for pool_id, health in pool_health.items()
            if health["status"] == "critical"
        ]

        if critical_pools:
            overall_health = "critical"
            issues.append(
                f"Critical connection pool issues: {', '.join(critical_pools)}"
            )

        warning_pools = [
            pool_id
            for pool_id, health in pool_health.items()
            if health["status"] == "warning"
        ]

        if warning_pools and overall_health == "healthy":
            overall_health = "warning"
            issues.append(f"Connection pool warnings: {', '.join(warning_pools)}")

        return {
            "overall_health": overall_health,
            "issues": issues,
            "query_performance": query_stats,
            "connection_pools": pool_health,
            "active_transactions": len(self.active_transactions),
            "completed_transactions": len(self.completed_transactions),
            "timestamp": datetime.now().isoformat(),
        }


# Decorator for automatic query performance tracking
def track_database_query(
    tracker: DatabasePerformanceTracker,
    connection_pool_id: str | None = None,
    transaction_id: str | None = None,
):
    """Decorator for automatic database query performance tracking"""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract query from arguments (assumes first arg is query string)
            query = args[0] if args else kwargs.get("query", "unknown_query")

            with tracker.track_query(
                query, connection_pool_id, transaction_id
            ) as context:
                try:
                    # Mark connection as acquired at function start
                    if "connection_acquired" in context:
                        context["connection_acquired"]()

                    result = func(*args, **kwargs)

                    # Extract rows affected if available in result
                    if hasattr(result, "rowcount"):
                        # Update rows affected in the current metric
                        pass  # This would need access to the current metric

                    return result

                except Exception as e:
                    logger.error(f"Database query failed in {func.__name__}: {e}")
                    raise

        return wrapper

    return decorator


# Global database performance tracker instance
_database_performance_tracker = None


def get_database_performance_tracker() -> DatabasePerformanceTracker:
    """Get global database performance tracker instance"""
    global _database_performance_tracker

    if _database_performance_tracker is None:
        _database_performance_tracker = DatabasePerformanceTracker()

    return _database_performance_tracker


def initialize_database_performance_tracking(
    retention_seconds: int = 3600,
) -> DatabasePerformanceTracker:
    """Initialize global database performance tracking"""
    global _database_performance_tracker

    _database_performance_tracker = DatabasePerformanceTracker(retention_seconds)
    logger.info("Global database performance tracking initialized")

    return _database_performance_tracker
