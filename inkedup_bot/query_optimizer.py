#!/usr/bin/env python3
"""
Advanced Query Optimizer for Batch Database Operations

This module provides intelligent query optimization, caching, and batch query processing
to improve database performance for high-volume operations.
"""

import hashlib
import logging
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of database queries for optimization."""

    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    AGGREGATE = "aggregate"
    JOIN = "join"


class QueryPriority(Enum):
    """Query execution priority levels."""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class QueryPlan:
    """Optimized execution plan for a query."""

    query_id: str
    original_query: str
    optimized_query: str
    query_type: QueryType
    estimated_cost: float
    estimated_rows: int
    use_cache: bool = False
    cache_ttl_seconds: int = 300
    indexes_used: list[str] = field(default_factory=list)
    optimization_applied: list[str] = field(default_factory=list)


@dataclass
class QueryResult:
    """Result of a query execution with metadata."""

    query_id: str
    result_data: Any
    execution_time_ms: float
    rows_affected: int
    cache_hit: bool = False
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class QueryMetrics:
    """Performance metrics for query execution."""

    total_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    average_execution_time_ms: float = 0.0
    total_execution_time_ms: float = 0.0
    slowest_query_time_ms: float = 0.0
    fastest_query_time_ms: float = float("inf")
    queries_by_type: dict[QueryType, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    optimization_savings_ms: float = 0.0


class QueryCache:
    """Intelligent query result caching system."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._access_times: dict[str, datetime] = {}
        self._ttl_map: dict[str, datetime] = {}
        self._lock = threading.RLock()

    def get(self, query_hash: str) -> Any | None:
        """Get cached query result if valid."""
        with self._lock:
            if query_hash not in self._cache:
                return None

            # Check TTL
            if query_hash in self._ttl_map:
                if datetime.now() > self._ttl_map[query_hash]:
                    self._remove_expired_entry(query_hash)
                    return None

            # Update access time for LRU
            self._access_times[query_hash] = datetime.now()
            self._cache.move_to_end(query_hash)

            return self._cache[query_hash]["result"]

    def put(self, query_hash: str, result: Any, ttl_seconds: int | None = None) -> bool:
        """Cache a query result."""
        with self._lock:
            # Evict if at capacity
            if len(self._cache) >= self.max_size:
                self._evict_lru()

            ttl = ttl_seconds or self.default_ttl
            expire_time = datetime.now() + timedelta(seconds=ttl)

            self._cache[query_hash] = {
                "result": result,
                "cached_at": datetime.now(),
                "size": len(str(result)) if result else 0,
            }
            self._access_times[query_hash] = datetime.now()
            self._ttl_map[query_hash] = expire_time

            return True

    def invalidate_pattern(self, pattern: str):
        """Invalidate cached entries matching a pattern."""
        with self._lock:
            keys_to_remove = []
            for key in self._cache.keys():
                if pattern in key:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                self._remove_expired_entry(key)

            logger.debug(
                f"Invalidated {len(keys_to_remove)} cache entries matching pattern: {pattern}"
            )

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            self._ttl_map.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_size = sum(entry["size"] for entry in self._cache.values())
            return {
                "entries": len(self._cache),
                "max_size": self.max_size,
                "total_size_bytes": total_size,
                "hit_rate": 0.0,  # Would be calculated by the optimizer
                "oldest_entry": (
                    min(self._access_times.values()) if self._access_times else None
                ),
                "newest_entry": (
                    max(self._access_times.values()) if self._access_times else None
                ),
            }

    def _evict_lru(self):
        """Evict least recently used entries."""
        if self._cache:
            # OrderedDict maintains insertion order, and we move_to_end on access
            oldest_key = next(iter(self._cache))
            self._remove_expired_entry(oldest_key)

    def _remove_expired_entry(self, key: str):
        """Remove an expired or evicted entry."""
        self._cache.pop(key, None)
        self._access_times.pop(key, None)
        self._ttl_map.pop(key, None)


class QueryOptimizer:
    """
    Advanced query optimizer with intelligent caching, query rewriting,
    and batch processing capabilities.
    """

    def __init__(self, cache_size: int = 1000, enable_optimization: bool = True):
        self.cache = QueryCache(max_size=cache_size)
        self.enable_optimization = enable_optimization
        self.metrics = QueryMetrics()
        self._metrics_lock = threading.Lock()

        # Query pattern analysis
        self._query_patterns: dict[str, list[str]] = defaultdict(list)
        self._common_queries: dict[str, int] = defaultdict(int)
        self._slow_queries: list[tuple[str, float]] = []

        # Index recommendations
        self._index_usage: dict[str, int] = defaultdict(int)
        self._missing_indexes: set[str] = set()

        # Batch query grouping
        self._pending_queries: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._batch_timers: dict[str, datetime] = {}

        logger.info("QueryOptimizer initialized")

    def analyze_query(self, query: str, parameters: tuple | None = None) -> QueryPlan:
        """Analyze a query and create an optimized execution plan."""
        query_hash = self._hash_query(query, parameters)
        query_type = self._identify_query_type(query)

        plan = QueryPlan(
            query_id=query_hash,
            original_query=query,
            optimized_query=query,
            query_type=query_type,
            estimated_cost=1.0,
            estimated_rows=100,
        )

        if not self.enable_optimization:
            return plan

        # Apply query optimizations
        optimized_query = query
        optimizations_applied = []

        # 1. Query rewriting optimizations
        if query_type == QueryType.SELECT:
            optimized_query, opt_list = self._optimize_select_query(query)
            optimizations_applied.extend(opt_list)

        elif query_type == QueryType.UPDATE:
            optimized_query, opt_list = self._optimize_update_query(query)
            optimizations_applied.extend(opt_list)

        elif query_type == QueryType.INSERT:
            optimized_query, opt_list = self._optimize_insert_query(query)
            optimizations_applied.extend(opt_list)

        # 2. Determine cache strategy
        plan.use_cache = self._should_cache_query(query, query_type)
        if plan.use_cache:
            plan.cache_ttl_seconds = self._calculate_cache_ttl(query, query_type)

        # 3. Index recommendations
        plan.indexes_used = self._analyze_index_usage(query)

        # 4. Cost estimation
        plan.estimated_cost = self._estimate_query_cost(optimized_query, query_type)
        plan.estimated_rows = self._estimate_result_size(optimized_query, query_type)

        plan.optimized_query = optimized_query
        plan.optimization_applied = optimizations_applied

        # Track query patterns for future optimization
        self._track_query_pattern(query, query_type)

        return plan

    async def execute_optimized_query(
        self, db_connection, plan: QueryPlan, parameters: tuple | None = None
    ) -> QueryResult:
        """Execute a query using the optimized plan."""
        start_time = time.time()
        cache_hit = False
        result_data = None

        # Try cache first
        if plan.use_cache:
            cached_result = self.cache.get(plan.query_id)
            if cached_result is not None:
                cache_hit = True
                result_data = cached_result

                with self._metrics_lock:
                    self.metrics.cache_hits += 1

        # Execute query if not cached
        if result_data is None:
            cursor = await db_connection.execute(plan.optimized_query, parameters or ())

            if plan.query_type == QueryType.SELECT:
                result_data = await cursor.fetchall()
            else:
                result_data = cursor.rowcount

            # Cache the result if appropriate
            if plan.use_cache and result_data is not None:
                self.cache.put(plan.query_id, result_data, plan.cache_ttl_seconds)

            with self._metrics_lock:
                self.metrics.cache_misses += 1

        # Calculate execution time
        execution_time = (time.time() - start_time) * 1000

        # Update metrics
        await self._update_query_metrics(plan, execution_time, result_data, cache_hit)

        return QueryResult(
            query_id=plan.query_id,
            result_data=result_data,
            execution_time_ms=execution_time,
            rows_affected=(
                len(result_data)
                if isinstance(result_data, list | tuple)
                else result_data or 0
            ),
            cache_hit=cache_hit,
        )

    async def execute_batch_queries(
        self,
        db_connection,
        queries: list[tuple[str, tuple | None]],
        optimize: bool = True,
    ) -> list[QueryResult]:
        """Execute multiple queries with batch optimization."""
        if not queries:
            return []

        results = []

        if optimize:
            # Group queries by type and pattern for optimization
            grouped_queries = self._group_queries_for_batch(queries)

            for group_type, group_queries in grouped_queries.items():
                if group_type == "bulk_insert":
                    batch_result = await self._execute_bulk_insert(
                        db_connection, group_queries
                    )
                    results.extend(batch_result)
                elif group_type == "bulk_select":
                    batch_result = await self._execute_bulk_select(
                        db_connection, group_queries
                    )
                    results.extend(batch_result)
                else:
                    # Execute individually with optimization
                    for query, params in group_queries:
                        plan = self.analyze_query(query, params)
                        result = await self.execute_optimized_query(
                            db_connection, plan, params
                        )
                        results.append(result)
        else:
            # Execute all queries individually without optimization
            for query, params in queries:
                plan = QueryPlan(
                    query_id=self._hash_query(query, params),
                    original_query=query,
                    optimized_query=query,
                    query_type=self._identify_query_type(query),
                    estimated_cost=1.0,
                    estimated_rows=100,
                )
                result = await self.execute_optimized_query(db_connection, plan, params)
                results.append(result)

        return results

    def _optimize_select_query(self, query: str) -> tuple[str, list[str]]:
        """Optimize SELECT queries."""
        optimized = query
        optimizations = []

        # Add LIMIT if missing for potentially large result sets
        if "LIMIT" not in query.upper() and "COUNT(*)" not in query.upper():
            if "ORDER BY" in query.upper():
                optimized = query + " LIMIT 1000"
            else:
                # Add ORDER BY for consistent results with LIMIT
                optimized = query + " ORDER BY rowid LIMIT 1000"
            optimizations.append("Added LIMIT clause")

        # Suggest covering indexes for common patterns
        if "WHERE" in query.upper():
            self._analyze_where_clause(query)
            optimizations.append("Analyzed WHERE clause for indexing")

        # Optimize JOIN operations
        if "JOIN" in query.upper():
            optimized, join_opts = self._optimize_joins(optimized)
            optimizations.extend(join_opts)

        return optimized, optimizations

    def _optimize_update_query(self, query: str) -> tuple[str, list[str]]:
        """Optimize UPDATE queries."""
        optimized = query
        optimizations = []

        # Add WHERE clause validation
        if "WHERE" not in query.upper():
            logger.warning(
                "UPDATE query without WHERE clause detected - potential performance issue"
            )
            optimizations.append("Warning: Missing WHERE clause")

        # Suggest indexes on UPDATE conditions
        if "WHERE" in query.upper():
            self._analyze_where_clause(query)
            optimizations.append("Analyzed UPDATE conditions for indexing")

        return optimized, optimizations

    def _optimize_insert_query(self, query: str) -> tuple[str, list[str]]:
        """Optimize INSERT queries."""
        optimized = query
        optimizations = []

        # Convert single INSERT to INSERT OR IGNORE/REPLACE if appropriate
        if "INSERT INTO" in query.upper() and "INSERT OR" not in query.upper():
            # This would require more sophisticated analysis of the use case
            optimizations.append("Analyzed INSERT pattern")

        return optimized, optimizations

    def _optimize_joins(self, query: str) -> tuple[str, list[str]]:
        """Optimize JOIN operations."""
        optimizations = []

        # Analyze JOIN order and suggest optimizations
        if "LEFT JOIN" in query.upper():
            optimizations.append("Analyzed LEFT JOIN performance")

        if "INNER JOIN" in query.upper():
            optimizations.append("Analyzed INNER JOIN performance")

        # For now, return the original query
        return query, optimizations

    def _analyze_where_clause(self, query: str):
        """Analyze WHERE clauses and suggest indexes."""
        # Extract column names from WHERE clause
        # This is a simplified version - a full implementation would use SQL parsing
        where_pos = query.upper().find("WHERE")
        if where_pos != -1:
            where_clause = (
                query[where_pos + 5 :].split("ORDER BY")[0].split("GROUP BY")[0]
            )

            # Simple pattern matching for common index opportunities
            for table in ["orders", "positions", "trades", "outcomes"]:
                if table in query.lower():
                    if "token_id" in where_clause.lower():
                        self._missing_indexes.add(f"{table}_token_id_idx")
                    if "market_slug" in where_clause.lower():
                        self._missing_indexes.add(f"{table}_market_slug_idx")
                    if "created_at" in where_clause.lower():
                        self._missing_indexes.add(f"{table}_created_at_idx")

    def _should_cache_query(self, query: str, query_type: QueryType) -> bool:
        """Determine if a query result should be cached."""
        if query_type != QueryType.SELECT:
            return False

        # Cache read-only queries that don't change frequently
        cache_indicators = [
            "outcomes",  # Market outcome data
            "positions",  # Current positions
            "COUNT(*)",  # Aggregate queries
            "market_slug",  # Market-specific queries
        ]

        return any(indicator in query.lower() for indicator in cache_indicators)

    def _calculate_cache_ttl(self, query: str, query_type: QueryType) -> int:
        """Calculate appropriate cache TTL for a query."""
        # Different TTL based on data volatility
        if "outcomes" in query.lower():
            return 30  # Market data changes frequently
        elif "positions" in query.lower():
            return 60  # Position data changes moderately
        elif "trades" in query.lower():
            return 300  # Historical trade data is more stable
        else:
            return 120  # Default TTL

    def _analyze_index_usage(self, query: str) -> list[str]:
        """Analyze which indexes would be beneficial for the query."""
        indexes = []

        # Simple heuristics - in practice, you'd query EXPLAIN QUERY PLAN
        if "token_id" in query.lower():
            indexes.append("token_id_idx")
            self._index_usage["token_id_idx"] += 1

        if "market_slug" in query.lower():
            indexes.append("market_slug_idx")
            self._index_usage["market_slug_idx"] += 1

        if "created_at" in query.lower() or "updated_at" in query.lower():
            indexes.append("timestamp_idx")
            self._index_usage["timestamp_idx"] += 1

        return indexes

    def _estimate_query_cost(self, query: str, query_type: QueryType) -> float:
        """Estimate the cost of executing a query."""
        base_cost = 1.0

        # Adjust cost based on query characteristics
        if "JOIN" in query.upper():
            base_cost *= 2.0

        if "ORDER BY" in query.upper():
            base_cost *= 1.5

        if "GROUP BY" in query.upper():
            base_cost *= 1.8

        if query_type == QueryType.INSERT:
            base_cost *= 0.5
        elif query_type == QueryType.UPDATE:
            base_cost *= 1.2
        elif query_type == QueryType.DELETE:
            base_cost *= 0.8

        return base_cost

    def _estimate_result_size(self, query: str, query_type: QueryType) -> int:
        """Estimate the number of rows that will be affected/returned."""
        if query_type in [QueryType.INSERT, QueryType.UPDATE, QueryType.DELETE]:
            return 1  # Default for modification queries

        # For SELECT queries, estimate based on patterns
        if "LIMIT" in query.upper():
            try:
                limit_pos = query.upper().find("LIMIT")
                limit_value = int(query[limit_pos + 5 :].split()[0])
                return min(limit_value, 1000)
            except Exception:
                pass

        return 100  # Default estimate

    def _identify_query_type(self, query: str) -> QueryType:
        """Identify the type of SQL query."""
        query_upper = query.strip().upper()

        if query_upper.startswith("SELECT"):
            if any(
                func in query_upper
                for func in ["COUNT(", "SUM(", "AVG(", "MAX(", "MIN("]
            ):
                return QueryType.AGGREGATE
            elif "JOIN" in query_upper:
                return QueryType.JOIN
            else:
                return QueryType.SELECT
        elif query_upper.startswith("INSERT"):
            return QueryType.INSERT
        elif query_upper.startswith("UPDATE"):
            return QueryType.UPDATE
        elif query_upper.startswith("DELETE"):
            return QueryType.DELETE
        else:
            return QueryType.SELECT

    def _hash_query(self, query: str, parameters: tuple | None = None) -> str:
        """Generate a hash for query caching."""
        query_text = query.strip().lower()
        param_str = str(parameters) if parameters else ""
        combined = f"{query_text}{param_str}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _track_query_pattern(self, query: str, query_type: QueryType):
        """Track query patterns for optimization analysis."""
        # Normalize query for pattern analysis
        normalized = self._normalize_query(query)
        pattern_hash = hashlib.md5(normalized.encode()).hexdigest()[:8]

        self._query_patterns[str(query_type)].append(pattern_hash)
        self._common_queries[pattern_hash] += 1

        # Keep track of most common queries
        if self._common_queries[pattern_hash] > 10:
            logger.debug(f"Frequently executed query pattern detected: {pattern_hash}")

    def _normalize_query(self, query: str) -> str:
        """Normalize query for pattern matching."""
        # Remove parameter values and normalize whitespace
        normalized = query.lower()

        # Replace common parameter patterns
        import re

        normalized = re.sub(r"'[^']*'", "?", normalized)  # String literals
        normalized = re.sub(r"\b\d+\b", "?", normalized)  # Numbers
        normalized = re.sub(r"\s+", " ", normalized)  # Multiple whitespace

        return normalized.strip()

    def _group_queries_for_batch(
        self, queries: list[tuple[str, tuple | None]]
    ) -> dict[str, list[tuple[str, tuple | None]]]:
        """Group queries for batch optimization."""
        groups = {"bulk_insert": [], "bulk_select": [], "other": []}

        for query, params in queries:
            query_upper = query.strip().upper()

            if query_upper.startswith("INSERT INTO"):
                # Check if it's the same table and can be batched
                groups["bulk_insert"].append((query, params))
            elif query_upper.startswith("SELECT") and "WHERE" in query_upper:
                # Group similar SELECT queries
                groups["bulk_select"].append((query, params))
            else:
                groups["other"].append((query, params))

        return {k: v for k, v in groups.items() if v}  # Remove empty groups

    async def _execute_bulk_insert(
        self, db_connection, queries: list[tuple[str, tuple | None]]
    ) -> list[QueryResult]:
        """Execute bulk insert operations."""
        results = []

        # Group by table for true bulk operations
        table_groups = defaultdict(list)

        for query, params in queries:
            # Extract table name (simplified)
            table_match = query.upper().split("INSERT INTO")[1].split("(")[0].strip()
            table_groups[table_match].append((query, params))

        # Execute each table group
        for table_name, table_queries in table_groups.items():
            start_time = time.time()

            try:
                # Execute all inserts for this table in a transaction
                await db_connection.execute("BEGIN TRANSACTION")

                rows_inserted = 0
                for query, params in table_queries:
                    cursor = await db_connection.execute(query, params or ())
                    rows_inserted += cursor.rowcount

                await db_connection.execute("COMMIT")

                execution_time = (time.time() - start_time) * 1000

                # Create a single result for the batch
                result = QueryResult(
                    query_id=f"bulk_insert_{table_name}_{int(time.time())}",
                    result_data=rows_inserted,
                    execution_time_ms=execution_time,
                    rows_affected=rows_inserted,
                    cache_hit=False,
                )
                results.append(result)

            except Exception as e:
                await db_connection.execute("ROLLBACK")
                logger.error(f"Bulk insert failed for table {table_name}: {e}")

                # Create error result
                result = QueryResult(
                    query_id=f"bulk_insert_error_{table_name}",
                    result_data=str(e),
                    execution_time_ms=0,
                    rows_affected=0,
                    cache_hit=False,
                )
                results.append(result)

        return results

    async def _execute_bulk_select(
        self, db_connection, queries: list[tuple[str, tuple | None]]
    ) -> list[QueryResult]:
        """Execute bulk select operations with optimization."""
        results = []

        # Execute each query individually but with shared optimization
        for query, params in queries:
            plan = self.analyze_query(query, params)
            result = await self.execute_optimized_query(db_connection, plan, params)
            results.append(result)

        return results

    async def _update_query_metrics(
        self,
        plan: QueryPlan,
        execution_time_ms: float,
        result_data: Any,
        cache_hit: bool,
    ):
        """Update query performance metrics."""
        with self._metrics_lock:
            self.metrics.total_queries += 1
            self.metrics.queries_by_type[plan.query_type] += 1

            if not cache_hit:
                # Only count actual execution time
                self.metrics.total_execution_time_ms += execution_time_ms

                # Update running average
                if self.metrics.total_queries > 1:
                    self.metrics.average_execution_time_ms = (
                        self.metrics.total_execution_time_ms
                        / (self.metrics.total_queries - self.metrics.cache_hits)
                    )
                else:
                    self.metrics.average_execution_time_ms = execution_time_ms

                # Track slowest and fastest
                if execution_time_ms > self.metrics.slowest_query_time_ms:
                    self.metrics.slowest_query_time_ms = execution_time_ms

                if execution_time_ms < self.metrics.fastest_query_time_ms:
                    self.metrics.fastest_query_time_ms = execution_time_ms

                # Track slow queries
                if execution_time_ms > 1000:  # Queries taking more than 1 second
                    self._slow_queries.append((plan.query_id, execution_time_ms))
                    if len(self._slow_queries) > 100:
                        self._slow_queries.pop(0)  # Keep only recent slow queries

            # Estimate optimization savings
            if len(plan.optimization_applied) > 0:
                estimated_savings = execution_time_ms * 0.2  # Assume 20% improvement
                self.metrics.optimization_savings_ms += estimated_savings

    def get_metrics(self) -> QueryMetrics:
        """Get current query optimization metrics."""
        with self._metrics_lock:
            # Calculate cache hit rate
            if self.metrics.total_queries > 0:
                _ = self.metrics.cache_hits / self.metrics.total_queries
            else:
                _ = 0.0

            # Create a copy of metrics with calculated values
            metrics_copy = QueryMetrics(
                total_queries=self.metrics.total_queries,
                cache_hits=self.metrics.cache_hits,
                cache_misses=self.metrics.cache_misses,
                average_execution_time_ms=self.metrics.average_execution_time_ms,
                total_execution_time_ms=self.metrics.total_execution_time_ms,
                slowest_query_time_ms=self.metrics.slowest_query_time_ms,
                fastest_query_time_ms=self.metrics.fastest_query_time_ms,
                queries_by_type=dict(self.metrics.queries_by_type),
                optimization_savings_ms=self.metrics.optimization_savings_ms,
            )

            return metrics_copy

    def get_recommendations(self) -> dict[str, Any]:
        """Get optimization recommendations based on analysis."""
        recommendations = {
            "missing_indexes": list(self._missing_indexes),
            "slow_queries": self._slow_queries[-10:],  # Last 10 slow queries
            "common_query_patterns": dict(list(self._common_queries.items())[:10]),
            "cache_stats": self.cache.get_stats(),
            "index_usage": dict(self._index_usage),
        }

        return recommendations

    def clear_cache(self):
        """Clear the query cache."""
        self.cache.clear()
        logger.info("Query cache cleared")

    def invalidate_cache_for_table(self, table_name: str):
        """Invalidate cached queries for a specific table."""
        self.cache.invalidate_pattern(table_name)
        logger.info(f"Cache invalidated for table: {table_name}")
