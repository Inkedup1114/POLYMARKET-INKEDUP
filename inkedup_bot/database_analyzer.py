"""
Database query analyzer and index optimizer for performance monitoring.
Analyzes query patterns, indexes, and provides optimization recommendations.
"""

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .database import DatabaseManager

log = logging.getLogger("database_analyzer")


@dataclass
class QueryPattern:
    """Represents a query pattern for analysis."""

    sql_template: str
    table_name: str
    where_columns: list[str] = field(default_factory=list)
    order_columns: list[str] = field(default_factory=list)
    group_columns: list[str] = field(default_factory=list)
    join_tables: list[str] = field(default_factory=list)
    operation_type: str = "SELECT"  # SELECT, INSERT, UPDATE, DELETE
    frequency: int = 0
    avg_execution_time: float = 0.0


@dataclass
class IndexRecommendation:
    """Represents an index recommendation."""

    table_name: str
    columns: list[str]
    index_type: str = "BTREE"  # BTREE, UNIQUE, PARTIAL
    priority: int = 1  # 1=High, 2=Medium, 3=Low
    reason: str = ""
    estimated_benefit: float = 0.0
    existing_coverage: bool = False


@dataclass
class IndexAnalysis:
    """Analysis results for database indexes."""

    existing_indexes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    missing_indexes: list[IndexRecommendation] = field(default_factory=list)
    redundant_indexes: list[str] = field(default_factory=list)
    query_patterns: list[QueryPattern] = field(default_factory=list)
    performance_issues: list[str] = field(default_factory=list)


class DatabaseAnalyzer:
    """
    Analyzes database query patterns and provides index optimization recommendations.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.query_patterns: dict[str, QueryPattern] = {}
        self.query_stats: list[dict[str, Any]] = []
        self.performance_threshold = 0.1  # 100ms threshold for slow queries

    async def analyze_database(self) -> IndexAnalysis:
        """Perform comprehensive database analysis."""
        log.info("Starting comprehensive database analysis...")

        analysis = IndexAnalysis()

        # 1. Analyze existing indexes
        analysis.existing_indexes = await self._analyze_existing_indexes()

        # 2. Analyze query patterns from codebase
        analysis.query_patterns = await self._analyze_query_patterns()

        # 3. Generate index recommendations
        analysis.missing_indexes = await self._generate_index_recommendations(
            analysis.existing_indexes, analysis.query_patterns
        )

        # 4. Find redundant indexes
        analysis.redundant_indexes = await self._find_redundant_indexes(
            analysis.existing_indexes
        )

        # 5. Identify performance issues
        analysis.performance_issues = await self._identify_performance_issues()

        log.info(
            f"Database analysis complete. Found {len(analysis.missing_indexes)} recommendations"
        )
        return analysis

    async def _analyze_existing_indexes(self) -> dict[str, list[dict[str, Any]]]:
        """Analyze existing database indexes."""
        indexes_by_table = defaultdict(list)

        async with self.db_manager.connection() as db:
            # Get all indexes
            async with db.execute(
                "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
            ) as cursor:
                rows = await cursor.fetchall()

                for row in rows:
                    index_name, table_name, sql = row

                    # Parse columns from CREATE INDEX statement
                    columns = self._parse_index_columns(sql)

                    # Get index info
                    async with db.execute(
                        f"PRAGMA index_info({index_name})"
                    ) as idx_cursor:
                        column_info = await idx_cursor.fetchall()

                    index_data = {
                        "name": index_name,
                        "columns": columns,
                        "sql": sql,
                        "column_details": [dict(row) for row in column_info],
                        "is_unique": "UNIQUE" in sql.upper(),
                        "is_partial": "WHERE" in sql.upper(),
                    }

                    indexes_by_table[table_name].append(index_data)

        return dict(indexes_by_table)

    def _parse_index_columns(self, create_index_sql: str) -> list[str]:
        """Parse column names from CREATE INDEX SQL."""
        # Extract columns from CREATE INDEX statement
        match = re.search(r"\(([^)]+)\)", create_index_sql)
        if match:
            columns_str = match.group(1)
            # Split by comma and clean up
            columns = [
                col.strip().strip('"').strip("'") for col in columns_str.split(",")
            ]
            return columns
        return []

    async def _analyze_query_patterns(self) -> list[QueryPattern]:
        """Analyze query patterns from the codebase."""
        patterns = []

        # Define common query patterns observed in the codebase
        query_patterns = [
            # Orders table queries
            QueryPattern(
                sql_template="SELECT * FROM orders WHERE id = ?",
                table_name="orders",
                where_columns=["id"],
                operation_type="SELECT",
                frequency=100,  # High frequency
            ),
            QueryPattern(
                sql_template="SELECT * FROM orders WHERE token_id = ?",
                table_name="orders",
                where_columns=["token_id"],
                operation_type="SELECT",
                frequency=80,
            ),
            QueryPattern(
                sql_template="SELECT * FROM orders WHERE market_slug = ?",
                table_name="orders",
                where_columns=["market_slug"],
                operation_type="SELECT",
                frequency=60,
            ),
            QueryPattern(
                sql_template="SELECT * FROM orders WHERE status = ?",
                table_name="orders",
                where_columns=["status"],
                operation_type="SELECT",
                frequency=70,
            ),
            QueryPattern(
                sql_template="UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                table_name="orders",
                where_columns=["id"],
                operation_type="UPDATE",
                frequency=50,
            ),
            # Positions table queries
            QueryPattern(
                sql_template="SELECT * FROM positions WHERE token_id = ?",
                table_name="positions",
                where_columns=["token_id"],
                operation_type="SELECT",
                frequency=90,
            ),
            QueryPattern(
                sql_template="SELECT * FROM positions WHERE market_slug = ?",
                table_name="positions",
                where_columns=["market_slug"],
                operation_type="SELECT",
                frequency=70,
            ),
            QueryPattern(
                sql_template="SELECT * FROM positions WHERE outcome_type = ?",
                table_name="positions",
                where_columns=["outcome_type"],
                operation_type="SELECT",
                frequency=50,
            ),
            QueryPattern(
                sql_template="SELECT SUM(notional_value) FROM positions WHERE market_slug = ?",
                table_name="positions",
                where_columns=["market_slug"],
                operation_type="SELECT",
                frequency=40,
            ),
            QueryPattern(
                sql_template="SELECT * FROM positions WHERE market_slug = ? GROUP BY outcome_type",
                table_name="positions",
                where_columns=["market_slug"],
                group_columns=["outcome_type"],
                operation_type="SELECT",
                frequency=30,
            ),
            # Trades table queries
            QueryPattern(
                sql_template="SELECT * FROM trades WHERE order_id = ?",
                table_name="trades",
                where_columns=["order_id"],
                operation_type="SELECT",
                frequency=60,
            ),
            QueryPattern(
                sql_template="SELECT * FROM trades WHERE token_id = ?",
                table_name="trades",
                where_columns=["token_id"],
                operation_type="SELECT",
                frequency=40,
            ),
            QueryPattern(
                sql_template="SELECT * FROM trades WHERE executed_at > ?",
                table_name="trades",
                where_columns=["executed_at"],
                operation_type="SELECT",
                frequency=30,
            ),
            # Outcome exposures queries
            QueryPattern(
                sql_template="SELECT * FROM outcome_exposures WHERE market_slug = ? AND outcome_id = ?",
                table_name="outcome_exposures",
                where_columns=["market_slug", "outcome_id"],
                operation_type="SELECT",
                frequency=80,
            ),
            QueryPattern(
                sql_template="SELECT * FROM outcome_exposures WHERE market_slug = ?",
                table_name="outcome_exposures",
                where_columns=["market_slug"],
                operation_type="SELECT",
                frequency=60,
            ),
            QueryPattern(
                sql_template="SELECT * FROM outcome_exposures WHERE last_updated > ?",
                table_name="outcome_exposures",
                where_columns=["last_updated"],
                operation_type="SELECT",
                frequency=40,
            ),
            # Market snapshots queries
            QueryPattern(
                sql_template="SELECT * FROM market_snapshots WHERE token_id = ?",
                table_name="market_snapshots",
                where_columns=["token_id"],
                operation_type="SELECT",
                frequency=50,
            ),
            QueryPattern(
                sql_template="SELECT * FROM market_snapshots WHERE market_slug = ?",
                table_name="market_snapshots",
                where_columns=["market_slug"],
                operation_type="SELECT",
                frequency=40,
            ),
            QueryPattern(
                sql_template="SELECT * FROM market_snapshots WHERE snapshot_at > ? ORDER BY snapshot_at DESC",
                table_name="market_snapshots",
                where_columns=["snapshot_at"],
                order_columns=["snapshot_at"],
                operation_type="SELECT",
                frequency=35,
            ),
            # Risk events queries
            QueryPattern(
                sql_template="SELECT * FROM risk_events WHERE token_id = ?",
                table_name="risk_events",
                where_columns=["token_id"],
                operation_type="SELECT",
                frequency=30,
            ),
            QueryPattern(
                sql_template="SELECT * FROM risk_events WHERE event_type = ?",
                table_name="risk_events",
                where_columns=["event_type"],
                operation_type="SELECT",
                frequency=25,
            ),
            # Exposure alerts queries
            QueryPattern(
                sql_template="SELECT * FROM exposure_alerts WHERE alert_type = ? AND acknowledged = ?",
                table_name="exposure_alerts",
                where_columns=["alert_type", "acknowledged"],
                operation_type="SELECT",
                frequency=35,
            ),
        ]

        return query_patterns

    async def _generate_index_recommendations(
        self,
        existing_indexes: dict[str, list[dict[str, Any]]],
        query_patterns: list[QueryPattern],
    ) -> list[IndexRecommendation]:
        """Generate index recommendations based on query patterns."""
        recommendations = []

        for pattern in query_patterns:
            table_name = pattern.table_name
            existing_table_indexes = existing_indexes.get(table_name, [])

            # Check if WHERE clause columns need indexes
            if pattern.where_columns:
                for single_column in pattern.where_columns:
                    if not self._has_index_covering_columns(
                        existing_table_indexes, [single_column]
                    ):
                        recommendations.append(
                            IndexRecommendation(
                                table_name=table_name,
                                columns=[single_column],
                                priority=self._calculate_priority(
                                    pattern.frequency, len(pattern.where_columns)
                                ),
                                reason=f"Frequent WHERE clause on {single_column} (frequency: {pattern.frequency})",
                                estimated_benefit=pattern.frequency * 0.1,
                            )
                        )

                # Multi-column index for compound WHERE clauses
                if len(pattern.where_columns) > 1:
                    if not self._has_index_covering_columns(
                        existing_table_indexes, pattern.where_columns
                    ):
                        recommendations.append(
                            IndexRecommendation(
                                table_name=table_name,
                                columns=pattern.where_columns,
                                priority=self._calculate_priority(
                                    pattern.frequency, len(pattern.where_columns)
                                ),
                                reason=f"Compound WHERE clause on {', '.join(pattern.where_columns)} (frequency: {pattern.frequency})",
                                estimated_benefit=pattern.frequency * 0.15,
                            )
                        )

            # Check if ORDER BY columns need indexes
            if pattern.order_columns:
                combined_columns = pattern.where_columns + pattern.order_columns
                if not self._has_index_covering_columns(
                    existing_table_indexes, combined_columns
                ):
                    recommendations.append(
                        IndexRecommendation(
                            table_name=table_name,
                            columns=combined_columns,
                            priority=self._calculate_priority(
                                pattern.frequency, len(combined_columns)
                            ),
                            reason=f"WHERE + ORDER BY optimization on {', '.join(combined_columns)}",
                            estimated_benefit=pattern.frequency * 0.12,
                        )
                    )

            # Check if GROUP BY columns need indexes
            if pattern.group_columns:
                combined_columns = pattern.where_columns + pattern.group_columns
                if not self._has_index_covering_columns(
                    existing_table_indexes, combined_columns
                ):
                    recommendations.append(
                        IndexRecommendation(
                            table_name=table_name,
                            columns=combined_columns,
                            priority=self._calculate_priority(
                                pattern.frequency, len(combined_columns)
                            ),
                            reason=f"WHERE + GROUP BY optimization on {', '.join(combined_columns)}",
                            estimated_benefit=pattern.frequency * 0.13,
                        )
                    )

        # Remove duplicates and sort by priority and estimated benefit
        unique_recommendations = self._deduplicate_recommendations(recommendations)
        unique_recommendations.sort(key=lambda x: (x.priority, -x.estimated_benefit))

        return unique_recommendations

    def _has_index_covering_columns(
        self, table_indexes: list[dict[str, Any]], columns: list[str]
    ) -> bool:
        """Check if existing indexes cover the specified columns."""
        for index in table_indexes:
            index_columns = index.get("columns", [])

            # Check if index covers all required columns (prefix match)
            if len(columns) <= len(index_columns):
                if all(col in index_columns[: len(columns)] for col in columns):
                    return True

        return False

    def _calculate_priority(self, frequency: int, column_count: int) -> int:
        """Calculate priority for index recommendation."""
        score = frequency * (1.0 / column_count)  # More columns = lower priority

        if score >= 70:
            return 1  # High priority
        elif score >= 40:
            return 2  # Medium priority
        else:
            return 3  # Low priority

    def _deduplicate_recommendations(
        self, recommendations: list[IndexRecommendation]
    ) -> list[IndexRecommendation]:
        """Remove duplicate recommendations."""
        seen = set()
        unique_recommendations = []

        for rec in recommendations:
            key = (rec.table_name, tuple(sorted(rec.columns)))
            if key not in seen:
                seen.add(key)
                unique_recommendations.append(rec)

        return unique_recommendations

    async def _find_redundant_indexes(
        self, existing_indexes: dict[str, list[dict[str, Any]]]
    ) -> list[str]:
        """Find potentially redundant indexes."""
        redundant = []

        for table_name, indexes in existing_indexes.items():
            for i, index1 in enumerate(indexes):
                for j, index2 in enumerate(indexes[i + 1 :], i + 1):
                    cols1 = index1.get("columns", [])
                    cols2 = index2.get("columns", [])

                    # Check if one index is a prefix of another
                    if len(cols1) < len(cols2) and cols2[: len(cols1)] == cols1:
                        redundant.append(
                            f"{table_name}.{index1['name']} (covered by {index2['name']})"
                        )
                    elif len(cols2) < len(cols1) and cols1[: len(cols2)] == cols2:
                        redundant.append(
                            f"{table_name}.{index2['name']} (covered by {index1['name']})"
                        )

        return redundant

    async def _identify_performance_issues(self) -> list[str]:
        """Identify potential performance issues."""
        issues = []

        async with self.db_manager.connection() as db:
            # Check for tables without primary keys
            async with db.execute(
                """
                SELECT name FROM sqlite_master 
                WHERE type = 'table' 
                AND name NOT IN ('sqlite_sequence', 'sqlite_stat1')
                """
            ) as cursor:
                tables = await cursor.fetchall()

                for (table_name,) in tables:
                    async with db.execute(
                        f"PRAGMA table_info({table_name})"
                    ) as info_cursor:
                        columns = await info_cursor.fetchall()
                        has_pk = any(col[5] for col in columns)  # pk column is index 5

                        if not has_pk:
                            issues.append(f"Table {table_name} has no primary key")

            # Check for large tables without proper indexing
            for table_name in ["orders", "trades", "positions", "market_snapshots"]:
                try:
                    async with db.execute(
                        f"SELECT COUNT(*) FROM {table_name}"
                    ) as cursor:
                        result = await cursor.fetchone()
                        if result and result[0] > 10000:  # Large table threshold
                            issues.append(
                                f"Large table {table_name} ({result[0]} rows) may need additional indexing"
                            )
                except Exception:
                    # Table may not exist
                    pass

        return issues

    async def benchmark_query_performance(
        self, queries: list[tuple[str, tuple]]
    ) -> dict[str, float]:
        """Benchmark query performance."""
        results = {}

        async with self.db_manager.connection() as db:
            for sql, params in queries:
                times = []

                # Run each query multiple times for accurate measurement
                for _ in range(5):
                    start_time = time.perf_counter()
                    async with db.execute(sql, params) as cursor:
                        await cursor.fetchall()
                    end_time = time.perf_counter()
                    times.append(end_time - start_time)

                avg_time = sum(times) / len(times)
                results[sql] = avg_time

        return results

    async def generate_optimization_report(self) -> str:
        """Generate a comprehensive optimization report."""
        analysis = await self.analyze_database()

        report = []
        report.append("DATABASE INDEX OPTIMIZATION REPORT")
        report.append("=" * 50)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Existing indexes summary
        report.append("EXISTING INDEXES:")
        report.append("-" * 20)
        total_indexes = sum(
            len(indexes) for indexes in analysis.existing_indexes.values()
        )
        report.append(f"Total indexes: {total_indexes}")

        for table_name, indexes in analysis.existing_indexes.items():
            report.append(f"\n{table_name} ({len(indexes)} indexes):")
            for index in indexes:
                cols = ", ".join(index.get("columns", []))
                unique_str = " [UNIQUE]" if index.get("is_unique") else ""
                report.append(f"  - {index['name']}: ({cols}){unique_str}")

        # Missing indexes recommendations
        report.append("\n\nRECOMMENDED INDEXES:")
        report.append("-" * 20)

        high_priority = [r for r in analysis.missing_indexes if r.priority == 1]
        medium_priority = [r for r in analysis.missing_indexes if r.priority == 2]
        low_priority = [r for r in analysis.missing_indexes if r.priority == 3]

        if high_priority:
            report.append("\nHIGH PRIORITY:")
            for rec in high_priority:
                cols = ", ".join(rec.columns)
                report.append(
                    f"  CREATE INDEX idx_{rec.table_name}_{('_'.join(rec.columns))} ON {rec.table_name} ({cols});"
                )
                report.append(f"    Reason: {rec.reason}")
                report.append(f"    Estimated benefit: {rec.estimated_benefit:.1f}")

        if medium_priority:
            report.append("\nMEDIUM PRIORITY:")
            for rec in medium_priority:
                cols = ", ".join(rec.columns)
                report.append(
                    f"  CREATE INDEX idx_{rec.table_name}_{('_'.join(rec.columns))} ON {rec.table_name} ({cols});"
                )
                report.append(f"    Reason: {rec.reason}")

        if low_priority:
            report.append("\nLOW PRIORITY:")
            for rec in low_priority:
                cols = ", ".join(rec.columns)
                report.append(
                    f"  CREATE INDEX idx_{rec.table_name}_{('_'.join(rec.columns))} ON {rec.table_name} ({cols});"
                )
                report.append(f"    Reason: {rec.reason}")

        # Redundant indexes
        if analysis.redundant_indexes:
            report.append("\n\nPOTENTIALLY REDUNDANT INDEXES:")
            report.append("-" * 30)
            for redundant in analysis.redundant_indexes:
                report.append(f"  - {redundant}")

        # Performance issues
        if analysis.performance_issues:
            report.append("\n\nPERFORMANCE ISSUES:")
            report.append("-" * 20)
            for issue in analysis.performance_issues:
                report.append(f"  - {issue}")

        report.append("\n\nRECOMMENDATIONS SUMMARY:")
        report.append("-" * 25)
        report.append(f"High priority indexes to create: {len(high_priority)}")
        report.append(f"Medium priority indexes to create: {len(medium_priority)}")
        report.append(f"Low priority indexes to create: {len(low_priority)}")
        report.append(
            f"Potentially redundant indexes: {len(analysis.redundant_indexes)}"
        )
        report.append(
            f"Performance issues identified: {len(analysis.performance_issues)}"
        )

        return "\n".join(report)
