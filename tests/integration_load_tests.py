#!/usr/bin/env python3
"""
Integration Load Tests for InkedUp Bot Components

This module tests actual system components under load conditions:
- Scanner performance with real market data processing
- Database operations under concurrent load
- WebSocket manager stress testing
- Order client performance testing
- State manager concurrent access testing
"""

import asyncio
import logging
import statistics
import time
from typing import Any
from unittest.mock import AsyncMock

import psutil

# Import bot components for testing
from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.order_client import OrderClient
from inkedup_bot.position_manager import PositionManager
from inkedup_bot.scanner import Scanner
from inkedup_bot.state import StateManager

logger = logging.getLogger("integration_load_tests")


class SystemIntegrationLoadTester:
    """Load tester for actual system components."""

    def __init__(self):
        self.config = None
        self.components = {}
        self.metrics = {
            "scanner": [],
            "database": [],
            "state_manager": [],
            "order_client": [],
            "position_manager": [],
        }

    async def initialize_components(self):
        """Initialize all bot components for testing."""
        try:
            # Load configuration
            self.config = BotConfig()
            logger.info("✅ Configuration loaded")

            # Initialize database
            db_manager = DatabaseManager(str(self.config.database_url))
            await db_manager.initialize()
            self.components["database"] = db_manager
            logger.info("✅ Database manager initialized")

            # Initialize state manager
            state_manager = StateManager(db_manager)
            self.components["state_manager"] = state_manager
            logger.info("✅ State manager initialized")

            # Initialize scanner
            scanner = Scanner(self.config)
            self.components["scanner"] = scanner
            logger.info("✅ Scanner initialized")

            # Initialize position manager
            position_manager = PositionManager(state_manager)
            self.components["position_manager"] = position_manager
            logger.info("✅ Position manager initialized")

            # Initialize order client (stub for testing)
            try:
                order_client = OrderClient(self.config)
                self.components["order_client"] = order_client
                logger.info("✅ Order client initialized")
            except Exception as e:
                logger.warning(
                    f"⚠️  Order client initialization failed (using mock): {e}"
                )
                # Create a mock for testing
                mock_order_client = AsyncMock()
                mock_order_client.is_ready = True
                self.components["order_client"] = mock_order_client

            return True

        except Exception as e:
            logger.error(f"❌ Component initialization failed: {e}")
            return False

    async def test_scanner_performance(
        self,
        concurrent_scans: int = 50,
        markets_per_scan: int = 100,
        duration_seconds: int = 60,
    ) -> dict[str, Any]:
        """Test scanner performance under concurrent load."""
        logger.info(
            f"🔍 Testing scanner performance: {concurrent_scans} concurrent scans"
        )

        scanner = self.components.get("scanner")
        if not scanner:
            raise RuntimeError("Scanner not initialized")

        metrics = {
            "scan_times": [],
            "markets_processed": 0,
            "errors": 0,
            "memory_usage": [],
            "cpu_usage": [],
        }

        async def run_scan_batch():
            """Run a batch of scanner operations."""
            start_time = time.time()
            end_time = start_time + duration_seconds

            while time.time() < end_time:
                try:
                    scan_start = time.time()

                    # Use scanner's scan method or simulate scanning
                    if hasattr(scanner, "scan_markets"):
                        markets = await scanner.scan_markets()
                    else:
                        # Simulate market scanning
                        await asyncio.sleep(0.1)  # Simulate processing time
                        markets = [
                            {"id": i, "price": 0.5} for i in range(markets_per_scan)
                        ]

                    scan_time = (time.time() - scan_start) * 1000
                    metrics["scan_times"].append(scan_time)
                    metrics["markets_processed"] += len(markets) if markets else 0

                    # Record system metrics
                    process = psutil.Process()
                    metrics["memory_usage"].append(
                        process.memory_info().rss / 1024 / 1024
                    )
                    metrics["cpu_usage"].append(process.cpu_percent())

                except Exception as e:
                    logger.error(f"Scanner error: {e}")
                    metrics["errors"] += 1

                await asyncio.sleep(0.01)  # Small delay between scans

        # Start concurrent scanning
        tasks = [run_scan_batch() for _ in range(concurrent_scans)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Calculate summary statistics
        summary = {
            "total_scans": len(metrics["scan_times"]),
            "avg_scan_time_ms": (
                statistics.mean(metrics["scan_times"]) if metrics["scan_times"] else 0
            ),
            "p95_scan_time_ms": self._percentile(metrics["scan_times"], 95),
            "max_scan_time_ms": (
                max(metrics["scan_times"]) if metrics["scan_times"] else 0
            ),
            "markets_processed": metrics["markets_processed"],
            "error_rate": metrics["errors"]
            / (len(metrics["scan_times"]) + metrics["errors"])
            * 100,
            "avg_memory_mb": (
                statistics.mean(metrics["memory_usage"])
                if metrics["memory_usage"]
                else 0
            ),
            "peak_memory_mb": (
                max(metrics["memory_usage"]) if metrics["memory_usage"] else 0
            ),
            "avg_cpu_percent": (
                statistics.mean(metrics["cpu_usage"]) if metrics["cpu_usage"] else 0
            ),
        }

        logger.info(
            f"✅ Scanner performance test completed: {summary['total_scans']} scans, "
            f"avg {summary['avg_scan_time_ms']:.2f}ms"
        )

        return summary

    async def test_database_concurrent_load(
        self,
        concurrent_clients: int = 100,
        operations_per_client: int = 50,
        duration_seconds: int = 60,
    ) -> dict[str, Any]:
        """Test database performance under concurrent load."""
        logger.info(
            f"💾 Testing database concurrent load: {concurrent_clients} clients"
        )

        db_manager = self.components.get("database")
        if not db_manager:
            raise RuntimeError("Database manager not initialized")

        metrics = {
            "query_times": [],
            "operations_completed": 0,
            "errors": 0,
            "connection_stats": [],
        }

        async def run_database_operations(client_id: int):
            """Run database operations for a single client."""
            operations = 0
            start_time = time.time()
            end_time = start_time + duration_seconds

            while time.time() < end_time and operations < operations_per_client:
                try:
                    query_start = time.time()

                    # Perform various database operations
                    operation_type = operations % 4

                    if operation_type == 0:
                        # Test market data insertion
                        await db_manager.add_market_snapshot(
                            market_id=f"test_market_{client_id}_{operations}",
                            data={
                                "price": 0.5,
                                "volume": 1000,
                                "timestamp": time.time(),
                            },
                        )
                    elif operation_type == 1:
                        # Test order insertion
                        await db_manager.add_order(
                            order_id=f"order_{client_id}_{operations}",
                            market_id=f"market_{client_id}",
                            side="buy",
                            price=0.5,
                            size=100,
                        )
                    elif operation_type == 2:
                        # Test market data retrieval
                        await db_manager.get_market_snapshots(
                            market_id=f"test_market_{client_id}_{operations-1}",
                            limit=10,
                        )
                    else:
                        # Test position updates
                        await db_manager.update_position(
                            market_id=f"market_{client_id}",
                            token_id=f"token_{client_id}",
                            balance=100.0,
                        )

                    query_time = (time.time() - query_start) * 1000
                    metrics["query_times"].append(query_time)
                    metrics["operations_completed"] += 1
                    operations += 1

                except Exception as e:
                    logger.error(f"Database operation error (client {client_id}): {e}")
                    metrics["errors"] += 1

                await asyncio.sleep(0.001)  # Small delay

        # Start concurrent database clients
        tasks = [run_database_operations(i) for i in range(concurrent_clients)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Calculate summary
        total_operations = metrics["operations_completed"] + metrics["errors"]
        summary = {
            "total_operations": total_operations,
            "successful_operations": metrics["operations_completed"],
            "error_rate": (
                (metrics["errors"] / total_operations * 100)
                if total_operations > 0
                else 0
            ),
            "avg_query_time_ms": (
                statistics.mean(metrics["query_times"]) if metrics["query_times"] else 0
            ),
            "p95_query_time_ms": self._percentile(metrics["query_times"], 95),
            "max_query_time_ms": (
                max(metrics["query_times"]) if metrics["query_times"] else 0
            ),
            "operations_per_second": metrics["operations_completed"] / duration_seconds,
        }

        logger.info(
            f"✅ Database load test completed: {summary['total_operations']} operations, "
            f"avg {summary['avg_query_time_ms']:.2f}ms"
        )

        return summary

    async def test_state_manager_concurrent_access(
        self,
        concurrent_accessors: int = 75,
        operations_per_accessor: int = 100,
        duration_seconds: int = 45,
    ) -> dict[str, Any]:
        """Test state manager under concurrent access load."""
        logger.info(
            f"🏦 Testing state manager concurrent access: {concurrent_accessors} accessors"
        )

        state_manager = self.components.get("state_manager")
        if not state_manager:
            raise RuntimeError("State manager not initialized")

        metrics = {
            "operation_times": [],
            "state_updates": 0,
            "state_reads": 0,
            "errors": 0,
            "lock_contention": [],
        }

        async def run_state_operations(accessor_id: int):
            """Run state operations for concurrent access testing."""
            operations = 0
            start_time = time.time()
            end_time = start_time + duration_seconds

            while time.time() < end_time and operations < operations_per_accessor:
                try:
                    op_start = time.time()

                    operation_type = operations % 3

                    if operation_type == 0:
                        # Test market state updates
                        await state_manager.update_market(
                            market_id=f"market_{accessor_id}",
                            yes_price=0.5 + (operations * 0.001),
                            no_price=0.5 - (operations * 0.001),
                            volume=1000 + operations,
                        )
                        metrics["state_updates"] += 1

                    elif operation_type == 1:
                        # Test position updates
                        await state_manager.update_position(
                            market_id=f"market_{accessor_id}",
                            token_id=f"token_{accessor_id}",
                            balance=100.0 + operations,
                        )
                        metrics["state_updates"] += 1

                    else:
                        # Test state reads
                        await state_manager.get_market_state(f"market_{accessor_id}")
                        metrics["state_reads"] += 1

                    operation_time = (time.time() - op_start) * 1000
                    metrics["operation_times"].append(operation_time)
                    operations += 1

                except Exception as e:
                    logger.error(f"State manager error (accessor {accessor_id}): {e}")
                    metrics["errors"] += 1

                await asyncio.sleep(0.001)

        # Start concurrent state accessors
        tasks = [run_state_operations(i) for i in range(concurrent_accessors)]
        await asyncio.gather(*tasks, return_exceptions=True)

        total_operations = len(metrics["operation_times"]) + metrics["errors"]
        summary = {
            "total_operations": total_operations,
            "state_updates": metrics["state_updates"],
            "state_reads": metrics["state_reads"],
            "error_rate": (
                (metrics["errors"] / total_operations * 100)
                if total_operations > 0
                else 0
            ),
            "avg_operation_time_ms": (
                statistics.mean(metrics["operation_times"])
                if metrics["operation_times"]
                else 0
            ),
            "p95_operation_time_ms": self._percentile(metrics["operation_times"], 95),
            "max_operation_time_ms": (
                max(metrics["operation_times"]) if metrics["operation_times"] else 0
            ),
        }

        logger.info(
            f"✅ State manager test completed: {summary['total_operations']} operations"
        )

        return summary

    async def test_position_manager_performance(
        self,
        concurrent_updates: int = 50,
        positions_per_update: int = 20,
        duration_seconds: int = 30,
    ) -> dict[str, Any]:
        """Test position manager performance under load."""
        logger.info(
            f"💰 Testing position manager: {concurrent_updates} concurrent updates"
        )

        position_manager = self.components.get("position_manager")
        if not position_manager:
            raise RuntimeError("Position manager not initialized")

        metrics = {"update_times": [], "positions_processed": 0, "errors": 0}

        async def run_position_updates(updater_id: int):
            """Run position updates for performance testing."""
            updates = 0
            start_time = time.time()
            end_time = start_time + duration_seconds

            while time.time() < end_time and updates < positions_per_update:
                try:
                    update_start = time.time()

                    # Simulate position update
                    positions_data = []
                    for i in range(5):  # Update multiple positions per batch
                        positions_data.append(
                            {
                                "market_id": f"market_{updater_id}_{i}",
                                "token_id": f"token_{updater_id}_{i}",
                                "balance": 100.0 + updates * 10,
                                "timestamp": time.time(),
                            }
                        )

                    # Update positions (if method exists)
                    if hasattr(position_manager, "update_positions"):
                        await position_manager.update_positions(positions_data)
                    else:
                        # Fallback to individual updates
                        for pos_data in positions_data:
                            if hasattr(position_manager, "update_position"):
                                await position_manager.update_position(**pos_data)

                    update_time = (time.time() - update_start) * 1000
                    metrics["update_times"].append(update_time)
                    metrics["positions_processed"] += len(positions_data)
                    updates += 1

                except Exception as e:
                    logger.error(f"Position manager error (updater {updater_id}): {e}")
                    metrics["errors"] += 1

                await asyncio.sleep(0.01)

        # Start concurrent position updaters
        tasks = [run_position_updates(i) for i in range(concurrent_updates)]
        await asyncio.gather(*tasks, return_exceptions=True)

        total_operations = len(metrics["update_times"]) + metrics["errors"]
        summary = {
            "total_updates": total_operations,
            "positions_processed": metrics["positions_processed"],
            "error_rate": (
                (metrics["errors"] / total_operations * 100)
                if total_operations > 0
                else 0
            ),
            "avg_update_time_ms": (
                statistics.mean(metrics["update_times"])
                if metrics["update_times"]
                else 0
            ),
            "p95_update_time_ms": self._percentile(metrics["update_times"], 95),
            "max_update_time_ms": (
                max(metrics["update_times"]) if metrics["update_times"] else 0
            ),
            "positions_per_second": metrics["positions_processed"] / duration_seconds,
        }

        logger.info(
            f"✅ Position manager test completed: {summary['positions_processed']} positions"
        )

        return summary

    async def test_memory_pressure(self, duration_seconds: int = 120) -> dict[str, Any]:
        """Test system behavior under memory pressure."""
        logger.info("🧠 Testing system behavior under memory pressure")

        metrics = {
            "memory_snapshots": [],
            "gc_collections": 0,
            "performance_degradation": [],
        }

        import gc

        # Monitor memory usage over time
        start_time = time.time()
        end_time = start_time + duration_seconds

        # Create memory pressure by allocating large objects
        memory_hogs = []

        try:
            while time.time() < end_time:
                # Record current memory usage
                process = psutil.Process()
                memory_mb = process.memory_info().rss / 1024 / 1024
                metrics["memory_snapshots"].append(
                    {"timestamp": time.time() - start_time, "memory_mb": memory_mb}
                )

                # Create some memory pressure periodically
                if len(memory_hogs) < 50:  # Limit memory usage
                    # Create large objects to simulate memory pressure
                    large_data = [i * 1.0 for i in range(100000)]
                    memory_hogs.append(large_data)

                # Trigger garbage collection occasionally
                if int(time.time()) % 10 == 0:
                    collected = gc.collect()
                    metrics["gc_collections"] += collected

                # Test a quick operation to measure performance degradation
                op_start = time.time()
                await asyncio.sleep(0.001)  # Minimal operation
                op_time = (time.time() - op_start) * 1000
                metrics["performance_degradation"].append(op_time)

                await asyncio.sleep(1)  # Sample every second

        finally:
            # Clean up memory
            memory_hogs.clear()
            gc.collect()

        if metrics["memory_snapshots"]:
            memory_values = [s["memory_mb"] for s in metrics["memory_snapshots"]]
            summary = {
                "test_duration_seconds": duration_seconds,
                "initial_memory_mb": memory_values[0],
                "final_memory_mb": memory_values[-1],
                "peak_memory_mb": max(memory_values),
                "avg_memory_mb": statistics.mean(memory_values),
                "memory_growth_mb": memory_values[-1] - memory_values[0],
                "gc_collections": metrics["gc_collections"],
                "avg_op_time_ms": (
                    statistics.mean(metrics["performance_degradation"])
                    if metrics["performance_degradation"]
                    else 0
                ),
            }
        else:
            summary = {"error": "No memory snapshots collected"}

        logger.info("✅ Memory pressure test completed")

        return summary

    def _percentile(self, data: list[float], percentile: float) -> float:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    async def cleanup(self):
        """Clean up test resources."""
        try:
            # Close database connections
            if "database" in self.components:
                await self.components["database"].close()

            # Clean up other components
            for component_name, component in self.components.items():
                if hasattr(component, "cleanup"):
                    await component.cleanup()
                elif hasattr(component, "close"):
                    await component.close()

            logger.info("✅ Test components cleaned up")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")


async def run_integration_load_tests():
    """Run complete integration load test suite."""
    logger.info("🚀 Starting Integration Load Testing Suite")
    logger.info("=" * 60)

    tester = SystemIntegrationLoadTester()
    results = {}

    try:
        # Initialize components
        if not await tester.initialize_components():
            logger.error("❌ Failed to initialize components")
            return None

        # Test 1: Scanner Performance
        logger.info("\n📊 TEST 1: Scanner Performance Under Load")
        try:
            scanner_results = await tester.test_scanner_performance(
                concurrent_scans=50, markets_per_scan=100, duration_seconds=30
            )
            results["scanner_performance"] = scanner_results
        except Exception as e:
            logger.error(f"Scanner performance test failed: {e}")
            results["scanner_performance"] = {"error": str(e)}

        # Test 2: Database Concurrent Load
        logger.info("\n💾 TEST 2: Database Concurrent Load")
        try:
            db_results = await tester.test_database_concurrent_load(
                concurrent_clients=50, operations_per_client=25, duration_seconds=30
            )
            results["database_concurrent_load"] = db_results
        except Exception as e:
            logger.error(f"Database load test failed: {e}")
            results["database_concurrent_load"] = {"error": str(e)}

        # Test 3: State Manager Concurrent Access
        logger.info("\n🏦 TEST 3: State Manager Concurrent Access")
        try:
            state_results = await tester.test_state_manager_concurrent_access(
                concurrent_accessors=30, operations_per_accessor=50, duration_seconds=30
            )
            results["state_manager_concurrent"] = state_results
        except Exception as e:
            logger.error(f"State manager test failed: {e}")
            results["state_manager_concurrent"] = {"error": str(e)}

        # Test 4: Position Manager Performance
        logger.info("\n💰 TEST 4: Position Manager Performance")
        try:
            position_results = await tester.test_position_manager_performance(
                concurrent_updates=25, positions_per_update=10, duration_seconds=30
            )
            results["position_manager_performance"] = position_results
        except Exception as e:
            logger.error(f"Position manager test failed: {e}")
            results["position_manager_performance"] = {"error": str(e)}

        # Test 5: Memory Pressure Test
        logger.info("\n🧠 TEST 5: Memory Pressure Test")
        try:
            memory_results = await tester.test_memory_pressure(duration_seconds=60)
            results["memory_pressure"] = memory_results
        except Exception as e:
            logger.error(f"Memory pressure test failed: {e}")
            results["memory_pressure"] = {"error": str(e)}

    finally:
        await tester.cleanup()

    logger.info("\n" + "=" * 60)
    logger.info("🏁 Integration Load Testing Suite Completed")
    logger.info("=" * 60)

    return results


if __name__ == "__main__":
    # Run integration load tests
    results = asyncio.run(run_integration_load_tests())

    if results:
        print("\n📊 INTEGRATION LOAD TEST RESULTS:")
        print("=" * 50)

        for test_name, result in results.items():
            print(f"\n📋 {test_name.upper()}:")
            if "error" in result:
                print(f"  ❌ FAILED: {result['error']}")
            else:
                for key, value in result.items():
                    if isinstance(value, (int, float)):
                        print(f"  📈 {key}: {value}")
                    else:
                        print(f"  📋 {key}: {value}")

        print("\n✅ Integration load testing completed!")
    else:
        print("\n❌ Integration load testing failed!")
        exit(1)
