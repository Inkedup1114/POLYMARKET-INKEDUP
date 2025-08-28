#!/usr/bin/env python3
"""
Comprehensive tests for the batch processing system.

This module tests all aspects of the batch processing implementation including:
- Batch operations (inserts, updates, deletes)
- Query optimization and caching
- Transaction batching and optimization
- Performance monitoring and metrics
- Error handling and recovery
"""

import asyncio
import os
import sys
import time
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from inkedup_bot.batch_monitoring import (
    AlertSeverity,
    BatchMonitor,
    MetricType,
    MonitoringConfig,
)
from inkedup_bot.batch_processor import (
    BatchConfig,
    BatchOperation,
    BatchPriority,
    BatchProcessor,
    BatchStrategy,
    BatchType,
)
from inkedup_bot.database_batched import BatchedDatabaseManager
from inkedup_bot.query_optimizer import QueryOptimizer, QueryType
from inkedup_bot.transaction_optimizer import (
    TransactionOperation,
    TransactionOptimizer,
    TransactionType,
)


class TestBatchProcessor(unittest.TestCase):
    """Test the core batch processor functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = BatchConfig(
            max_batch_size=10,
            max_wait_time_ms=100,
            strategy=BatchStrategy.HYBRID,
            enable_metrics=True,
        )
        self.mock_db = Mock()
        self.processor = BatchProcessor(self.mock_db, self.config)

    def tearDown(self):
        """Clean up after tests."""
        asyncio.run(self.processor.stop())

    def test_batch_processor_initialization(self):
        """Test batch processor initialization."""
        self.assertEqual(self.processor.config.max_batch_size, 10)
        self.assertEqual(self.processor.config.strategy, BatchStrategy.HYBRID)
        self.assertIsNotNone(self.processor.queue)
        self.assertIsNotNone(self.processor.metrics)

    def test_batch_operation_creation(self):
        """Test creating batch operations."""
        operation = BatchOperation(
            operation_id="test_op_1",
            batch_type=BatchType.INSERT,
            table_name="orders",
            data={"id": "order_1", "price": 100.0},
            priority=BatchPriority.HIGH,
        )

        self.assertEqual(operation.operation_id, "test_op_1")
        self.assertEqual(operation.batch_type, BatchType.INSERT)
        self.assertEqual(operation.table_name, "orders")
        self.assertEqual(operation.priority, BatchPriority.HIGH)

    async def test_submit_operation(self):
        """Test submitting operations to batch processor."""
        await self.processor.start()

        operation = BatchOperation(
            operation_id="test_submit",
            batch_type=BatchType.INSERT,
            table_name="orders",
            data={"id": "order_submit", "price": 200.0},
        )

        success = await self.processor.submit_operation(operation)
        self.assertTrue(success)

        # Check that metrics were updated
        metrics = await self.processor.get_metrics()
        self.assertEqual(metrics.total_operations, 1)

    async def test_batch_insert_submission(self):
        """Test submitting batch insert operations."""
        await self.processor.start()

        records = [
            {"id": "order_1", "price": 100.0},
            {"id": "order_2", "price": 200.0},
            {"id": "order_3", "price": 300.0},
        ]

        success = await self.processor.submit_batch_insert(
            "orders", records, BatchPriority.NORMAL
        )
        self.assertTrue(success)

        # Allow some processing time
        await asyncio.sleep(0.2)

        metrics = await self.processor.get_metrics()
        self.assertEqual(metrics.total_operations, 3)


class TestQueryOptimizer(unittest.TestCase):
    """Test the query optimizer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.optimizer = QueryOptimizer(cache_size=100, enable_optimization=True)

    def test_query_optimizer_initialization(self):
        """Test query optimizer initialization."""
        self.assertTrue(self.optimizer.enable_optimization)
        self.assertIsNotNone(self.optimizer.cache)
        self.assertIsNotNone(self.optimizer.metrics)

    def test_analyze_select_query(self):
        """Test analyzing SELECT queries."""
        query = "SELECT * FROM orders WHERE token_id = ? AND market_slug = ?"
        parameters = ("token_1", "market_1")

        plan = self.optimizer.analyze_query(query, parameters)

        self.assertEqual(plan.query_type, QueryType.SELECT)
        self.assertIn("Added LIMIT clause", plan.optimization_applied)
        self.assertTrue(plan.use_cache)

    def test_analyze_insert_query(self):
        """Test analyzing INSERT queries."""
        query = "INSERT INTO orders (id, token_id, price) VALUES (?, ?, ?)"
        parameters = ("order_1", "token_1", 100.0)

        plan = self.optimizer.analyze_query(query, parameters)

        self.assertEqual(plan.query_type, QueryType.INSERT)
        self.assertFalse(plan.use_cache)  # INSERT queries shouldn't be cached

    def test_query_caching(self):
        """Test query result caching."""
        query_hash = "test_query_hash"
        test_result = [{"id": "order_1", "price": 100.0}]

        # Cache the result
        self.optimizer.cache.put(query_hash, test_result, ttl_seconds=60)

        # Retrieve from cache
        cached_result = self.optimizer.cache.get(query_hash)
        self.assertEqual(cached_result, test_result)

        # Test cache miss
        missing_result = self.optimizer.cache.get("nonexistent_hash")
        self.assertIsNone(missing_result)

    def test_cache_invalidation(self):
        """Test cache invalidation patterns."""
        # Cache some results
        self.optimizer.cache.put("orders_query_1", {"data": "test1"})
        self.optimizer.cache.put("positions_query_1", {"data": "test2"})
        self.optimizer.cache.put("orders_query_2", {"data": "test3"})

        # Invalidate orders-related queries
        self.optimizer.cache.invalidate_pattern("orders")

        # Check that orders queries were invalidated but positions weren't
        self.assertIsNone(self.optimizer.cache.get("orders_query_1"))
        self.assertIsNone(self.optimizer.cache.get("orders_query_2"))
        self.assertIsNotNone(self.optimizer.cache.get("positions_query_1"))


class TestTransactionOptimizer(unittest.TestCase):
    """Test the transaction optimizer functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.optimizer = TransactionOptimizer(max_batch_size=5, batch_timeout_ms=100)

    def test_transaction_optimizer_initialization(self):
        """Test transaction optimizer initialization."""
        self.assertEqual(self.optimizer.max_batch_size, 5)
        self.assertEqual(self.optimizer.batch_timeout_ms, 100)
        self.assertIsNotNone(self.optimizer.deadlock_detector)
        self.assertIsNotNone(self.optimizer.metrics)

    def test_create_transaction_plan(self):
        """Test creating transaction execution plans."""
        operations = [
            TransactionOperation(
                operation_id="op_1",
                operation_type="insert",
                table_name="orders",
                sql_query="INSERT INTO orders (id, price) VALUES (?, ?)",
                parameters=("order_1", 100.0),
            ),
            TransactionOperation(
                operation_id="op_2",
                operation_type="update",
                table_name="orders",
                sql_query="UPDATE orders SET status = ? WHERE id = ?",
                parameters=("FILLED", "order_1"),
            ),
        ]

        plan = self.optimizer.create_transaction_plan(operations)

        self.assertEqual(len(plan.operations), 2)
        self.assertEqual(plan.transaction_type, TransactionType.WRITE_ONLY)
        self.assertIn("orders", plan.tables_involved)
        self.assertGreater(plan.estimated_duration_ms, 0)

    def test_deadlock_detection(self):
        """Test deadlock detection functionality."""
        detector = self.optimizer.deadlock_detector

        # Request locks for transaction 1
        success1 = detector.request_locks("tx_1", {"table_A", "table_B"})
        self.assertTrue(success1)

        # Request locks for transaction 2 - should succeed (different tables initially)
        success2 = detector.request_locks("tx_2", {"table_C"})
        self.assertTrue(success2)

        # Try to create a potential deadlock scenario
        # This would require more complex setup in a real deadlock scenario

        # Clean up locks
        detector.release_locks("tx_1")
        detector.release_locks("tx_2")

    def test_transaction_batching_eligibility(self):
        """Test determining which transactions can be batched."""
        # Read-only operations should be batchable
        read_ops = [
            TransactionOperation(
                "op_1",
                "select",
                "orders",
                "SELECT * FROM orders WHERE id = ?",
                ("order_1",),
            )
        ]
        read_plan = self.optimizer.create_transaction_plan(read_ops)
        self.assertTrue(read_plan.can_batch)

        # Mixed operations with low complexity should be batchable
        mixed_ops = [
            TransactionOperation(
                "op_1",
                "insert",
                "orders",
                "INSERT INTO orders VALUES (?, ?)",
                ("order_1", 100),
            ),
            TransactionOperation(
                "op_2",
                "select",
                "orders",
                "SELECT * FROM orders WHERE id = ?",
                ("order_1",),
            ),
        ]
        mixed_plan = self.optimizer.create_transaction_plan(mixed_ops)
        self.assertTrue(mixed_plan.can_batch)


class TestBatchedDatabaseManager(unittest.TestCase):
    """Test the batched database manager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_db = ":memory:"
        self.config = BatchConfig(
            max_batch_size=5,
            max_wait_time_ms=100,
            strategy=BatchStrategy.IMMEDIATE,  # Use immediate for testing
        )
        self.db_manager = BatchedDatabaseManager(self.test_db, self.config)

    async def asyncSetUp(self):
        """Set up async test fixtures."""
        await self.db_manager.initialize()
        await self.db_manager.initialize_batch_processing()

    async def asyncTearDown(self):
        """Clean up async test fixtures."""
        await self.db_manager.shutdown_batch_processing()

    async def test_batch_insert_orders(self):
        """Test batch insertion of orders."""
        orders = [
            {
                "id": "test_order_1",
                "token_id": "token_1",
                "market_slug": "test_market",
                "side": "BUY",
                "price": 0.5,
                "size": 100.0,
                "status": "OPEN",
                "notional_value": 50.0,
                "outcome_type": "YES",
            },
            {
                "id": "test_order_2",
                "token_id": "token_2",
                "market_slug": "test_market",
                "side": "SELL",
                "price": 0.6,
                "size": 200.0,
                "status": "OPEN",
                "notional_value": 120.0,
                "outcome_type": "NO",
            },
        ]

        success = await self.db_manager.batch_insert_orders(orders, BatchPriority.HIGH)
        self.assertTrue(success)

        # Verify insertion by querying
        retrieved_orders = await self.db_manager.batch_get_orders(
            ["test_order_1", "test_order_2"]
        )
        self.assertEqual(len(retrieved_orders), 2)

    async def test_batch_update_orders(self):
        """Test batch updating of orders."""
        # First insert some orders
        orders = [
            {
                "id": "update_test_1",
                "token_id": "token_1",
                "market_slug": "test_market",
                "side": "BUY",
                "price": 0.5,
                "size": 100.0,
                "status": "OPEN",
                "notional_value": 50.0,
                "outcome_type": "YES",
            }
        ]

        await self.db_manager.batch_insert_orders(orders)

        # Now update them
        updates = [("update_test_1", {"status": "FILLED", "filled_at": datetime.now()})]
        success = await self.db_manager.batch_update_orders(updates, BatchPriority.HIGH)
        self.assertTrue(success)

    async def test_batch_queries(self):
        """Test batch query operations."""
        # Insert test data first
        orders = [
            {
                "id": f"query_test_{i}",
                "token_id": f"token_{i}",
                "market_slug": "query_market",
                "side": "BUY",
                "price": 0.5,
                "size": 100.0,
                "status": "OPEN",
                "notional_value": 50.0,
                "outcome_type": "YES",
            }
            for i in range(3)
        ]

        await self.db_manager.batch_insert_orders(orders)

        # Test batch retrieval
        order_ids = ["query_test_0", "query_test_1", "query_test_2"]
        retrieved_orders = await self.db_manager.batch_get_orders(order_ids)

        self.assertEqual(len(retrieved_orders), 3)
        self.assertEqual(retrieved_orders[0]["id"], "query_test_0")


class TestBatchMonitoring(unittest.TestCase):
    """Test the batch monitoring system."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_batch_processor = Mock()
        self.mock_batch_processor.get_metrics = AsyncMock()

        self.config = MonitoringConfig(
            collection_interval_seconds=1, enable_alerting=True
        )

        self.monitor = BatchMonitor(self.mock_batch_processor, config=self.config)

    async def asyncTearDown(self):
        """Clean up async test fixtures."""
        await self.monitor.stop_monitoring()

    def test_monitoring_initialization(self):
        """Test monitoring system initialization."""
        self.assertEqual(self.monitor.config.collection_interval_seconds, 1)
        self.assertTrue(self.monitor.config.enable_alerting)
        self.assertIsNotNone(self.monitor._performance_snapshots)
        self.assertIsNotNone(self.monitor._alerts)

    def test_alert_creation(self):
        """Test alert creation and management."""
        # Create a test alert
        alert = asyncio.run(
            self.monitor._create_alert(
                severity=AlertSeverity.WARNING,
                metric_type=MetricType.PERFORMANCE,
                component="test_component",
                message="Test alert message",
                current_value=0.8,
                threshold_value=0.7,
                timestamp=datetime.now(),
            )
        )

        # Check that alert was stored
        active_alerts = self.monitor.get_active_alerts()
        self.assertEqual(len(active_alerts), 1)
        self.assertEqual(active_alerts[0].component, "test_component")
        self.assertEqual(active_alerts[0].severity, AlertSeverity.WARNING)

    def test_alert_callback_system(self):
        """Test alert callback execution."""
        callback_called = []

        def test_callback(alert):
            callback_called.append(alert)

        self.monitor.add_alert_callback(test_callback)

        # Create an alert
        asyncio.run(
            self.monitor._create_alert(
                severity=AlertSeverity.ERROR,
                metric_type=MetricType.ERROR_RATE,
                component="callback_test",
                message="Callback test alert",
                current_value=0.9,
                threshold_value=0.8,
                timestamp=datetime.now(),
            )
        )

        # Verify callback was called
        self.assertEqual(len(callback_called), 1)
        self.assertEqual(callback_called[0].component, "callback_test")


class TestIntegrationScenarios(unittest.TestCase):
    """Test integration scenarios with multiple components."""

    async def test_end_to_end_batch_processing(self):
        """Test complete end-to-end batch processing workflow."""
        # Set up components
        batch_config = BatchConfig(
            max_batch_size=5,
            max_wait_time_ms=100,
            strategy=BatchStrategy.IMMEDIATE,
            enable_metrics=True,
        )

        db_manager = BatchedDatabaseManager(":memory:", batch_config)
        await db_manager.initialize()
        await db_manager.initialize_batch_processing()

        try:
            # Test data
            test_orders = [
                {
                    "id": f"integration_order_{i}",
                    "token_id": f"token_{i}",
                    "market_slug": "integration_market",
                    "side": "BUY" if i % 2 == 0 else "SELL",
                    "price": 0.5 + (i * 0.1),
                    "size": 100.0 + i,
                    "status": "OPEN",
                    "notional_value": (0.5 + (i * 0.1)) * (100.0 + i),
                    "outcome_type": "YES" if i % 2 == 0 else "NO",
                }
                for i in range(10)
            ]

            # Batch insert
            start_time = time.time()
            success = await db_manager.batch_insert_orders(
                test_orders, BatchPriority.HIGH
            )
            insert_time = time.time() - start_time

            self.assertTrue(success)
            self.assertLess(insert_time, 2.0)  # Should complete within 2 seconds

            # Batch query
            order_ids = [order["id"] for order in test_orders[:5]]
            retrieved_orders = await db_manager.batch_get_orders(order_ids)

            self.assertEqual(len(retrieved_orders), 5)

            # Batch update
            updates = [(order["id"], {"status": "FILLED"}) for order in test_orders[:3]]
            update_success = await db_manager.batch_update_orders(
                updates, BatchPriority.HIGH
            )

            self.assertTrue(update_success)

            # Verify metrics were collected
            if db_manager._batch_processor:
                metrics = await db_manager.get_batch_metrics()
                self.assertIsNotNone(metrics)
                self.assertGreater(metrics["total_operations"], 0)

        finally:
            await db_manager.shutdown_batch_processing()

    async def test_performance_under_load(self):
        """Test batch processing performance under load."""
        batch_config = BatchConfig(
            max_batch_size=50,
            max_wait_time_ms=200,
            strategy=BatchStrategy.HYBRID,
            enable_metrics=True,
        )

        db_manager = BatchedDatabaseManager(":memory:", batch_config)
        await db_manager.initialize()
        await db_manager.initialize_batch_processing()

        try:
            # Generate large dataset
            large_dataset = []
            for i in range(1000):
                large_dataset.append(
                    {
                        "id": f"load_test_{i}",
                        "token_id": f"token_{i % 50}",
                        "market_slug": f"market_{i % 10}",
                        "side": "BUY" if i % 2 == 0 else "SELL",
                        "price": 0.1 + (i % 100) * 0.01,
                        "size": 10.0 + (i % 50),
                        "status": "OPEN",
                        "notional_value": (0.1 + (i % 100) * 0.01) * (10.0 + (i % 50)),
                        "outcome_type": "YES" if i % 2 == 0 else "NO",
                    }
                )

            # Measure performance
            start_time = time.time()
            success = await db_manager.batch_insert_orders(
                large_dataset, BatchPriority.NORMAL
            )
            total_time = time.time() - start_time

            self.assertTrue(success)

            # Performance assertions
            throughput = len(large_dataset) / total_time
            self.assertGreater(throughput, 100)  # Should process at least 100 ops/sec
            self.assertLess(total_time, 30.0)  # Should complete within 30 seconds

            # Verify all data was inserted
            sample_ids = [
                f"load_test_{i}" for i in range(0, 1000, 100)
            ]  # Sample every 100th
            retrieved_orders = await db_manager.batch_get_orders(sample_ids)
            self.assertEqual(
                len(retrieved_orders), 10
            )  # Should retrieve all sampled orders

        finally:
            await db_manager.shutdown_batch_processing()


if __name__ == "__main__":
    # Configure asyncio test runner for Python 3.8+
    import asyncio

    class AsyncTestRunner:
        def run_async_test(self, test_method):
            """Run an async test method."""
            return asyncio.run(test_method())

    # Create test suite
    test_suite = unittest.TestSuite()

    # Add test cases
    test_classes = [
        TestBatchProcessor,
        TestQueryOptimizer,
        TestTransactionOptimizer,
        TestBatchedDatabaseManager,
        TestBatchMonitoring,
        TestIntegrationScenarios,
    ]

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    # Print summary
    print("\nTest Results:")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Failures: {len(result.failures)}")
    print(f"  Errors: {len(result.errors)}")
    print(
        f"  Success rate: {(result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100:.1f}%"
    )
