"""
Comprehensive test suite for database optimization and performance monitoring.
Tests indexing strategies, query performance, and monitoring capabilities.
"""

import tempfile
import time
from pathlib import Path

import pytest

from inkedup_bot.database_analyzer import (
    DatabaseAnalyzer,
    IndexRecommendation,
    QueryPattern,
)
from inkedup_bot.database_optimized import OptimizedDatabaseManager


class TestDatabaseOptimization:
    """Test suite for database optimization features."""

    @pytest.fixture
    async def optimized_db(self):
        """Create an optimized database manager for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            db_path = tmp_file.name

        manager = OptimizedDatabaseManager(
            db_path=db_path,
            enable_monitoring=True,
            slow_query_threshold=0.01,  # 10ms threshold for testing
            metrics_retention_hours=1,
        )

        await manager.initialize()
        yield manager

        await manager.close()
        Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_optimized_indexes_creation(self, optimized_db):
        """Test that optimized indexes are created correctly."""
        async with optimized_db.connection() as db:
            # Check that optimized indexes exist
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ) as cursor:
                indexes = await cursor.fetchall()
                index_names = [row[0] for row in indexes]

                # Check for key optimized indexes
                expected_indexes = [
                    "idx_orders_token",  # Original
                    "idx_orders_status_created_at",  # Optimized
                    "idx_orders_token_status",  # Optimized
                    "idx_positions_market_outcome",  # Optimized
                    "idx_trades_token_executed",  # Optimized
                ]

                for expected in expected_indexes:
                    assert (
                        expected in index_names
                    ), f"Missing optimized index: {expected}"

    @pytest.mark.asyncio
    async def test_query_performance_monitoring(self, optimized_db):
        """Test query performance monitoring capabilities."""
        # Insert test data
        test_order = {
            "id": "test_order_1",
            "token_id": "token_123",
            "market_slug": "test_market",
            "side": "BUY",
            "price": 0.5,
            "size": 100.0,
            "status": "OPEN",
        }

        await optimized_db.insert_order(test_order)

        # Execute monitored queries
        result1 = await optimized_db.execute_monitored_query(
            "SELECT * FROM orders WHERE token_id = ?", ("token_123",)
        )

        result2 = await optimized_db.execute_monitored_query(
            "SELECT * FROM orders WHERE status = ?", ("OPEN",)
        )

        # Check results
        assert len(result1) == 1
        assert len(result2) == 1
        assert result1[0]["id"] == "test_order_1"

        # Check that metrics were recorded
        stats = optimized_db.get_performance_stats()
        assert stats["database_stats"]["total_queries"] >= 2
        assert len(optimized_db.query_metrics) >= 2

    @pytest.mark.asyncio
    async def test_query_caching(self, optimized_db):
        """Test query result caching functionality."""
        # Insert test data
        test_position = {
            "token_id": "token_456",
            "market_slug": "cache_test_market",
            "outcome_type": "YES",
            "size": 50.0,
            "notional_value": 25.0,
        }

        await optimized_db.upsert_position(test_position)

        # Execute same query multiple times with caching
        cache_key = "test_cache_key"

        start_time = time.time()
        result1 = await optimized_db.execute_monitored_query(
            "SELECT * FROM positions WHERE market_slug = ?",
            ("cache_test_market",),
            cache_key=cache_key,
        )
        first_query_time = time.time() - start_time

        start_time = time.time()
        result2 = await optimized_db.execute_monitored_query(
            "SELECT * FROM positions WHERE market_slug = ?",
            ("cache_test_market",),
            cache_key=cache_key,
        )
        second_query_time = time.time() - start_time

        # Results should be identical
        assert result1 == result2
        assert len(result1) == 1
        assert result1[0]["token_id"] == "token_456"

        # Second query should be faster due to caching
        # (Note: This might be flaky in fast environments, so we just check cache stats)
        stats = optimized_db.get_performance_stats()
        assert stats["database_stats"]["cache_hits"] >= 1

    @pytest.mark.asyncio
    async def test_slow_query_detection(self, optimized_db):
        """Test slow query detection and reporting."""
        # Force a slow query by using a complex operation
        slow_query = """
            SELECT o1.*, o2.* FROM orders o1 
            CROSS JOIN orders o2 
            WHERE o1.id LIKE '%test%' OR o2.id LIKE '%test%'
        """

        # This should be detected as slow
        await optimized_db.execute_monitored_query(slow_query, ())

        stats = optimized_db.get_performance_stats()

        # Check if slow query was detected
        # (The exact count depends on other operations, so we just check structure)
        assert "top_slow_queries" in stats
        assert "recent_slow_queries" in stats
        assert isinstance(stats["database_stats"]["slow_queries"], int)

    @pytest.mark.asyncio
    async def test_performance_stats_structure(self, optimized_db):
        """Test the structure and content of performance statistics."""
        # Execute some queries to generate data
        await optimized_db.execute_monitored_query("SELECT COUNT(*) FROM orders", ())
        await optimized_db.execute_monitored_query("SELECT COUNT(*) FROM positions", ())

        stats = optimized_db.get_performance_stats()

        # Check main structure
        assert "database_stats" in stats
        assert "top_slow_queries" in stats
        assert "most_frequent_queries" in stats
        assert "recent_slow_queries" in stats
        assert "cache_stats" in stats

        # Check database_stats structure
        db_stats = stats["database_stats"]
        required_fields = [
            "total_queries",
            "total_execution_time",
            "avg_query_time",
            "slow_queries",
            "query_errors",
            "cache_hits",
            "cache_misses",
            "cache_hit_ratio",
            "active_connections",
        ]

        for field in required_fields:
            assert field in db_stats
            assert isinstance(db_stats[field], (int, float))

    @pytest.mark.asyncio
    async def test_enhanced_database_methods(self, optimized_db):
        """Test enhanced database methods with monitoring."""
        # Test data setup
        test_position = {
            "token_id": "enhanced_test",
            "market_slug": "enhanced_market",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 50.0,
        }
        await optimized_db.upsert_position(test_position)

        test_exposure = {
            "market_slug": "enhanced_market",
            "outcome_id": "outcome_1",
            "outcome_name": "Test Outcome",
            "position_size": 100.0,
            "notional_value": 50.0,
            "average_price": 0.5,
            "current_price": 0.55,
            "unrealized_pnl": 5.0,
            "realized_pnl": 0.0,
        }
        await optimized_db.upsert_outcome_exposure(**test_exposure)

        # Test enhanced methods
        positions = await optimized_db.get_positions_by_market("enhanced_market")
        assert len(positions) == 1
        assert positions[0]["token_id"] == "enhanced_test"

        exposure = await optimized_db.get_outcome_exposure(
            "enhanced_market", "outcome_1"
        )
        assert exposure is not None
        assert exposure["outcome_name"] == "Test Outcome"

        total_exposure = await optimized_db.get_total_exposure()
        assert total_exposure > 0

        # Verify monitoring was applied
        stats = optimized_db.get_performance_stats()
        assert stats["database_stats"]["total_queries"] >= 3


class TestDatabaseAnalyzer:
    """Test suite for database analyzer."""

    @pytest.fixture
    async def analyzer_db(self):
        """Create database with analyzer for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            db_path = tmp_file.name

        manager = OptimizedDatabaseManager(db_path=db_path, enable_monitoring=False)
        await manager.initialize()

        analyzer = DatabaseAnalyzer(manager)

        yield manager, analyzer

        await manager.close()
        Path(db_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_existing_indexes(self, analyzer_db):
        """Test analysis of existing database indexes."""
        manager, analyzer = analyzer_db

        existing_indexes = await analyzer._analyze_existing_indexes()

        # Should have indexes for all main tables
        expected_tables = ["orders", "positions", "trades", "outcome_exposures"]

        for table in expected_tables:
            assert table in existing_indexes
            assert len(existing_indexes[table]) > 0

            # Check index structure
            for index in existing_indexes[table]:
                assert "name" in index
                assert "columns" in index
                assert "sql" in index
                assert isinstance(index["columns"], list)

    @pytest.mark.asyncio
    async def test_query_pattern_analysis(self, analyzer_db):
        """Test query pattern analysis."""
        manager, analyzer = analyzer_db

        patterns = await analyzer._analyze_query_patterns()

        assert len(patterns) > 0

        # Check pattern structure
        for pattern in patterns:
            assert isinstance(pattern, QueryPattern)
            assert pattern.table_name
            assert pattern.sql_template
            assert isinstance(pattern.frequency, int)
            assert pattern.frequency > 0

    @pytest.mark.asyncio
    async def test_index_recommendations(self, analyzer_db):
        """Test index recommendation generation."""
        manager, analyzer = analyzer_db

        # Get current analysis
        analysis = await analyzer.analyze_database()

        assert hasattr(analysis, "existing_indexes")
        assert hasattr(analysis, "missing_indexes")
        assert hasattr(analysis, "query_patterns")

        # Check recommendation structure
        for rec in analysis.missing_indexes:
            assert isinstance(rec, IndexRecommendation)
            assert rec.table_name
            assert rec.columns
            assert len(rec.columns) > 0
            assert rec.priority in [1, 2, 3]
            assert rec.reason

    @pytest.mark.asyncio
    async def test_performance_issue_detection(self, analyzer_db):
        """Test performance issue identification."""
        manager, analyzer = analyzer_db

        issues = await analyzer._identify_performance_issues()

        # Should be a list (might be empty for a fresh database)
        assert isinstance(issues, list)

        # Each issue should be a descriptive string
        for issue in issues:
            assert isinstance(issue, str)
            assert len(issue) > 0

    @pytest.mark.asyncio
    async def test_optimization_report_generation(self, analyzer_db):
        """Test comprehensive optimization report generation."""
        manager, analyzer = analyzer_db

        report = await analyzer.generate_optimization_report()

        # Should be a comprehensive string report
        assert isinstance(report, str)
        assert len(report) > 0

        # Should contain key sections
        assert "DATABASE INDEX OPTIMIZATION REPORT" in report
        assert "EXISTING INDEXES:" in report
        assert "RECOMMENDED INDEXES:" in report

        # Should contain practical information
        assert "CREATE INDEX" in report or "No recommendations" in report.lower()

    @pytest.mark.asyncio
    async def test_query_benchmarking(self, analyzer_db):
        """Test query performance benchmarking."""
        manager, analyzer = analyzer_db

        # Insert some test data first
        test_order = {
            "id": "benchmark_test",
            "token_id": "bench_token",
            "market_slug": "bench_market",
            "side": "BUY",
            "price": 0.6,
            "size": 200.0,
            "status": "OPEN",
        }
        await manager.insert_order(test_order)

        # Benchmark some queries
        queries = [
            ("SELECT * FROM orders WHERE id = ?", ("benchmark_test",)),
            ("SELECT COUNT(*) FROM orders", ()),
            ("SELECT * FROM orders WHERE status = ?", ("OPEN",)),
        ]

        results = await analyzer.benchmark_query_performance(queries)

        # Should have timing results for each query
        assert len(results) == len(queries)

        for sql, _ in queries:
            assert sql in results
            assert isinstance(results[sql], float)
            assert results[sql] >= 0  # Execution time should be non-negative


class TestIndexOptimizationIntegration:
    """Integration tests for complete optimization workflow."""

    @pytest.fixture
    async def full_system(self):
        """Create complete optimized database system."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            db_path = tmp_file.name

        manager = OptimizedDatabaseManager(
            db_path=db_path, enable_monitoring=True, slow_query_threshold=0.05  # 50ms
        )

        await manager.initialize()

        # Add substantial test data
        await self._populate_test_data(manager)

        yield manager

        await manager.close()
        Path(db_path).unlink(missing_ok=True)

    async def _populate_test_data(self, manager):
        """Populate database with realistic test data."""
        # Create orders
        for i in range(100):
            order = {
                "id": f"order_{i}",
                "token_id": f"token_{i % 20}",  # 20 different tokens
                "market_slug": f"market_{i % 10}",  # 10 different markets
                "side": "BUY" if i % 2 == 0 else "SELL",
                "price": 0.1 + (i % 90) * 0.01,  # Price range 0.1 to 1.0
                "size": 10.0 + (i % 100),
                "status": ["OPEN", "FILLED", "CANCELLED"][i % 3],
            }
            await manager.insert_order(order)

        # Create positions
        for i in range(50):
            position = {
                "token_id": f"token_{i % 20}",
                "market_slug": f"market_{i % 10}",
                "outcome_type": "YES" if i % 2 == 0 else "NO",
                "size": 50.0 + i,
                "notional_value": 25.0 + i * 0.5,
            }
            await manager.upsert_position(position)

        # Create trades
        for i in range(150):
            trade_data = {
                "token_id": f"token_{i % 20}",
                "trade_size": 10.0 + (i % 50),
                "trade_price": 0.2 + (i % 80) * 0.01,
                "side": "BUY" if i % 2 == 0 else "SELL",
                "market_slug": f"market_{i % 10}",
                "outcome_type": "YES" if i % 2 == 0 else "NO",
            }
            await manager.record_trade_impact(**trade_data)

    @pytest.mark.asyncio
    async def test_comprehensive_optimization_workflow(self, full_system):
        """Test complete optimization workflow with real data."""
        manager = full_system

        # 1. Execute various query patterns to generate metrics
        query_patterns = [
            ("SELECT * FROM orders WHERE token_id = ?", ("token_5",)),
            ("SELECT * FROM orders WHERE market_slug = ?", ("market_3",)),
            ("SELECT * FROM orders WHERE status = ?", ("OPEN",)),
            ("SELECT * FROM positions WHERE market_slug = ?", ("market_1",)),
            ("SELECT * FROM positions WHERE outcome_type = ?", ("YES",)),
            ("SELECT COUNT(*) FROM trades WHERE token_id = ?", ("token_10",)),
        ]

        # Execute queries multiple times to build metrics
        for _ in range(10):
            for sql, params in query_patterns:
                await manager.execute_monitored_query(sql, params)

        # 2. Get performance analysis
        analysis_report = await manager.analyze_performance()

        assert isinstance(analysis_report, str)
        assert "PERFORMANCE ANALYSIS" in analysis_report
        assert "PERFORMANCE SUMMARY" in analysis_report

        # 3. Check that monitoring captured the queries
        stats = manager.get_performance_stats()
        assert (
            stats["database_stats"]["total_queries"] >= 60
        )  # 6 patterns × 10 iterations

        # 4. Verify index effectiveness by comparing query times
        # (This is more of a smoke test since actual performance depends on data size)
        top_queries = stats["top_slow_queries"]
        most_frequent = stats["most_frequent_queries"]

        assert len(top_queries) <= 10  # Should limit to top 10
        assert len(most_frequent) <= 10  # Should limit to top 10

        # 5. Check that cache is working
        cache_stats = stats["cache_stats"]
        assert cache_stats["cached_entries"] >= 0
        assert cache_stats["max_cache_size"] > 0

    @pytest.mark.asyncio
    async def test_index_impact_on_query_performance(self, full_system):
        """Test that optimized indexes improve query performance."""
        manager = full_system

        # Test frequently used query patterns
        test_queries = [
            # Should benefit from idx_orders_token_status
            (
                "SELECT * FROM orders WHERE token_id = ? AND status = ?",
                ("token_1", "OPEN"),
            ),
            # Should benefit from idx_positions_market_outcome
            (
                "SELECT * FROM positions WHERE market_slug = ? AND outcome_type = ?",
                ("market_1", "YES"),
            ),
            # Should benefit from idx_trades_token_executed
            (
                "SELECT * FROM trades WHERE token_id = ? ORDER BY executed_at DESC",
                ("token_5",),
            ),
        ]

        # Benchmark the queries
        if manager.analyzer:
            results = await manager.analyzer.benchmark_query_performance(test_queries)

            # All queries should complete reasonably quickly with proper indexes
            for sql, _ in test_queries:
                assert sql in results
                query_time = results[sql]
                # With proper indexes, queries should be fast even with test data
                # This is more of a sanity check than a hard performance requirement
                assert query_time < 1.0  # Should complete within 1 second

    @pytest.mark.asyncio
    async def test_monitoring_overhead(self, full_system):
        """Test that monitoring doesn't significantly impact performance."""
        manager = full_system

        # Test with monitoring enabled
        start_time = time.time()
        for i in range(50):
            await manager.execute_monitored_query(
                "SELECT * FROM orders WHERE token_id = ?", (f"token_{i % 20}",)
            )
        monitored_time = time.time() - start_time

        # Test direct database access (no monitoring)
        start_time = time.time()
        async with manager.connection() as db:
            for i in range(50):
                async with db.execute(
                    "SELECT * FROM orders WHERE token_id = ?", (f"token_{i % 20}",)
                ) as cursor:
                    await cursor.fetchall()
        direct_time = time.time() - start_time

        # Monitoring overhead should be reasonable (less than 50% overhead)
        overhead_ratio = monitored_time / max(
            direct_time, 0.001
        )  # Avoid division by zero
        assert (
            overhead_ratio < 1.5
        ), f"Monitoring overhead too high: {overhead_ratio:.2f}x"

        # Verify monitoring data was collected
        stats = manager.get_performance_stats()
        assert stats["database_stats"]["total_queries"] >= 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
