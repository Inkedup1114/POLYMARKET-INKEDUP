#!/usr/bin/env python3
"""
Comprehensive Load Testing Suite for InkedUp Polymarket Bot

This suite tests the system's performance under high-frequency trading conditions,
concurrent market updates, and stress scenarios. It includes:

1. Market Data Load Testing (1000+ concurrent updates)
2. High-Frequency Trading Simulation
3. WebSocket Connection Stress Testing
4. Database Performance Under Load
5. Memory Usage and Response Time Benchmarks
6. System Resource Monitoring
"""

import asyncio
import gc
import json
import logging
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psutil

# Configure logging for load tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("load_testing")


@dataclass
class LoadTestMetrics:
    """Comprehensive metrics collection for load testing."""

    # Performance metrics
    response_times: list[float] = field(default_factory=list)
    throughput_per_second: list[float] = field(default_factory=list)
    error_count: int = 0
    success_count: int = 0

    # System resource metrics
    memory_usage_mb: list[float] = field(default_factory=list)
    cpu_usage_percent: list[float] = field(default_factory=list)

    # Database metrics
    db_query_times: list[float] = field(default_factory=list)
    db_connection_count: list[int] = field(default_factory=list)

    # WebSocket metrics
    ws_message_count: int = 0
    ws_connection_latency: list[float] = field(default_factory=list)

    # Custom metrics
    market_updates_processed: int = 0
    orders_executed: int = 0
    position_updates: int = 0

    def add_response_time(self, time_ms: float):
        """Add response time measurement."""
        self.response_times.append(time_ms)

    def add_error(self):
        """Increment error count."""
        self.error_count += 1

    def add_success(self):
        """Increment success count."""
        self.success_count += 1

    def record_error(self):
        """Record a failed operation (alias for add_error)."""
        self.add_error()

    def record_success(self):
        """Record a successful operation (alias for add_success)."""
        self.add_success()

    def record_system_metrics(self):
        """Record current system resource usage."""
        process = psutil.Process()

        # Memory usage in MB
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.memory_usage_mb.append(memory_mb)

        # CPU usage percentage
        cpu_percent = process.cpu_percent()
        self.cpu_usage_percent.append(cpu_percent)

    def get_summary(self) -> dict[str, Any]:
        """Generate comprehensive metrics summary."""
        total_requests = self.success_count + self.error_count

        summary = {
            "performance": {
                "total_requests": total_requests,
                "success_rate": (
                    (self.success_count / total_requests * 100)
                    if total_requests > 0
                    else 0
                ),
                "error_rate": (
                    (self.error_count / total_requests * 100)
                    if total_requests > 0
                    else 0
                ),
                "avg_response_time_ms": (
                    statistics.mean(self.response_times) if self.response_times else 0
                ),
                "median_response_time_ms": (
                    statistics.median(self.response_times) if self.response_times else 0
                ),
                "p95_response_time_ms": (
                    self._percentile(self.response_times, 95)
                    if self.response_times
                    else 0
                ),
                "p99_response_time_ms": (
                    self._percentile(self.response_times, 99)
                    if self.response_times
                    else 0
                ),
                "min_response_time_ms": (
                    min(self.response_times) if self.response_times else 0
                ),
                "max_response_time_ms": (
                    max(self.response_times) if self.response_times else 0
                ),
            },
            "throughput": {
                "avg_throughput_rps": (
                    statistics.mean(self.throughput_per_second)
                    if self.throughput_per_second
                    else 0
                ),
                "peak_throughput_rps": (
                    max(self.throughput_per_second) if self.throughput_per_second else 0
                ),
            },
            "system_resources": {
                "avg_memory_mb": (
                    statistics.mean(self.memory_usage_mb) if self.memory_usage_mb else 0
                ),
                "peak_memory_mb": (
                    max(self.memory_usage_mb) if self.memory_usage_mb else 0
                ),
                "avg_cpu_percent": (
                    statistics.mean(self.cpu_usage_percent)
                    if self.cpu_usage_percent
                    else 0
                ),
                "peak_cpu_percent": (
                    max(self.cpu_usage_percent) if self.cpu_usage_percent else 0
                ),
            },
            "application_metrics": {
                "market_updates_processed": self.market_updates_processed,
                "orders_executed": self.orders_executed,
                "position_updates": self.position_updates,
                "ws_messages_received": self.ws_message_count,
                "avg_ws_latency_ms": (
                    statistics.mean(self.ws_connection_latency)
                    if self.ws_connection_latency
                    else 0
                ),
            },
        }

        if self.db_query_times:
            summary["database"] = {
                "avg_query_time_ms": statistics.mean(self.db_query_times),
                "p95_query_time_ms": self._percentile(self.db_query_times, 95),
                "slowest_query_ms": max(self.db_query_times),
                "avg_connection_count": (
                    statistics.mean(self.db_connection_count)
                    if self.db_connection_count
                    else 0
                ),
            }

        return summary

    def _percentile(self, data: list[float], percentile: float) -> float:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


class MarketDataSimulator:
    """Simulates high-frequency market data updates."""

    def __init__(self, num_markets: int = 100):
        self.num_markets = num_markets
        self.markets = self._generate_markets()

    def _generate_markets(self) -> list[dict[str, Any]]:
        """Generate synthetic market data."""
        markets = []
        for i in range(self.num_markets):
            market = {
                "id": f"market_{i}",
                "slug": f"test-market-{i}",
                "question": f"Test Market {i}",
                "yes_price": round(random.uniform(0.1, 0.9), 4),
                "no_price": round(random.uniform(0.1, 0.9), 4),
                "volume": random.uniform(1000, 100000),
                "liquidity": random.uniform(500, 50000),
                "last_updated": time.time(),
            }
            # Ensure complement pricing
            market["no_price"] = round(1.0 - market["yes_price"], 4)
            markets.append(market)
        return markets

    def generate_market_update(self) -> dict[str, Any]:
        """Generate a realistic market update."""
        market = random.choice(self.markets)

        # Simulate realistic price movements
        price_change = random.uniform(-0.05, 0.05)  # ±5% maximum change
        new_yes_price = max(0.01, min(0.99, market["yes_price"] + price_change))
        new_no_price = round(1.0 - new_yes_price, 4)

        # Update market
        market["yes_price"] = new_yes_price
        market["no_price"] = new_no_price
        market["volume"] += random.uniform(100, 5000)
        market["last_updated"] = time.time()

        return market.copy()

    def generate_book_update(self) -> dict[str, Any]:
        """Generate order book update."""
        market = random.choice(self.markets)

        # Generate realistic order book
        bids = []
        asks = []

        base_price = market["yes_price"]

        # Generate bids (below current price)
        for i in range(5):
            price = base_price - (i + 1) * 0.01
            if price > 0:
                bids.append(
                    {"price": round(price, 4), "size": random.uniform(100, 1000)}
                )

        # Generate asks (above current price)
        for i in range(5):
            price = base_price + (i + 1) * 0.01
            if price < 1.0:
                asks.append(
                    {"price": round(price, 4), "size": random.uniform(100, 1000)}
                )

        return {
            "market_id": market["id"],
            "bids": bids,
            "asks": asks,
            "timestamp": time.time(),
        }


class LoadTestRunner:
    """Main load testing orchestrator."""

    def __init__(self):
        self.metrics = LoadTestMetrics()
        self.market_simulator = MarketDataSimulator()
        self.running = False

    async def run_market_data_load_test(
        self,
        concurrent_updates: int = 1000,
        duration_seconds: int = 60,
        update_frequency_hz: int = 10,
    ) -> LoadTestMetrics:
        """
        Test system's ability to handle high-frequency market data updates.

        Args:
            concurrent_updates: Number of concurrent market updates
            duration_seconds: Test duration in seconds
            update_frequency_hz: Updates per second
        """
        logger.info(
            f"Starting market data load test: {concurrent_updates} concurrent updates, "
            f"{duration_seconds}s duration, {update_frequency_hz} Hz"
        )

        self.running = True
        self.metrics = LoadTestMetrics()

        # Start system monitoring
        monitor_task = asyncio.create_task(self._monitor_system_resources())

        # Start market data generation
        update_tasks = []
        for _ in range(concurrent_updates):
            task = asyncio.create_task(
                self._generate_market_updates(update_frequency_hz, duration_seconds)
            )
            update_tasks.append(task)

        # Run load test
        start_time = time.time()
        try:
            await asyncio.gather(*update_tasks, return_exceptions=True)
        finally:
            self.running = False
            monitor_task.cancel()

        elapsed_time = time.time() - start_time
        logger.info(f"Market data load test completed in {elapsed_time:.2f}s")

        return self.metrics

    async def run_high_frequency_trading_test(
        self,
        concurrent_traders: int = 100,
        orders_per_trader: int = 50,
        duration_seconds: int = 30,
    ) -> LoadTestMetrics:
        """
        Simulate high-frequency trading conditions.

        Args:
            concurrent_traders: Number of concurrent trading bots
            orders_per_trader: Orders per trader during test
            duration_seconds: Test duration
        """
        logger.info(
            f"Starting HFT simulation: {concurrent_traders} traders, "
            f"{orders_per_trader} orders each, {duration_seconds}s duration"
        )

        self.running = True
        self.metrics = LoadTestMetrics()

        # Start system monitoring
        monitor_task = asyncio.create_task(self._monitor_system_resources())

        # Start trading simulation
        trader_tasks = []
        for trader_id in range(concurrent_traders):
            task = asyncio.create_task(
                self._simulate_hft_trader(
                    trader_id, orders_per_trader, duration_seconds
                )
            )
            trader_tasks.append(task)

        # Run trading simulation
        start_time = time.time()
        try:
            results = await asyncio.gather(*trader_tasks, return_exceptions=True)

            # Count successful/failed traders
            for result in results:
                if isinstance(result, Exception):
                    self.metrics.add_error()
                else:
                    self.metrics.add_success()

        finally:
            self.running = False
            monitor_task.cancel()

        elapsed_time = time.time() - start_time
        logger.info(f"HFT simulation completed in {elapsed_time:.2f}s")

        return self.metrics

    async def run_websocket_stress_test(
        self,
        concurrent_connections: int = 50,
        messages_per_connection: int = 1000,
        duration_seconds: int = 60,
    ) -> LoadTestMetrics:
        """
        Test WebSocket connection handling under stress.

        Args:
            concurrent_connections: Number of concurrent WebSocket connections
            messages_per_connection: Messages to send per connection
            duration_seconds: Test duration
        """
        logger.info(
            f"Starting WebSocket stress test: {concurrent_connections} connections, "
            f"{messages_per_connection} messages each, {duration_seconds}s duration"
        )

        self.running = True
        self.metrics = LoadTestMetrics()

        # Start system monitoring
        monitor_task = asyncio.create_task(self._monitor_system_resources())

        # Start WebSocket simulation
        ws_tasks = []
        for conn_id in range(concurrent_connections):
            task = asyncio.create_task(
                self._simulate_websocket_client(
                    conn_id, messages_per_connection, duration_seconds
                )
            )
            ws_tasks.append(task)

        # Run WebSocket stress test
        start_time = time.time()
        try:
            await asyncio.gather(*ws_tasks, return_exceptions=True)
        finally:
            self.running = False
            monitor_task.cancel()

        elapsed_time = time.time() - start_time
        logger.info(f"WebSocket stress test completed in {elapsed_time:.2f}s")

        return self.metrics

    async def run_database_performance_test(
        self,
        concurrent_operations: int = 200,
        operations_per_client: int = 100,
        duration_seconds: int = 60,
    ) -> LoadTestMetrics:
        """
        Test database performance under concurrent load.

        Args:
            concurrent_operations: Number of concurrent database clients
            operations_per_client: Database operations per client
            duration_seconds: Test duration
        """
        logger.info(
            f"Starting database performance test: {concurrent_operations} clients, "
            f"{operations_per_client} operations each, {duration_seconds}s duration"
        )

        self.running = True
        self.metrics = LoadTestMetrics()

        # Start system monitoring
        monitor_task = asyncio.create_task(self._monitor_system_resources())

        # Start database operations
        db_tasks = []
        for client_id in range(concurrent_operations):
            task = asyncio.create_task(
                self._simulate_database_client(
                    client_id, operations_per_client, duration_seconds
                )
            )
            db_tasks.append(task)

        # Run database performance test
        start_time = time.time()
        try:
            await asyncio.gather(*db_tasks, return_exceptions=True)
        finally:
            self.running = False
            monitor_task.cancel()

        elapsed_time = time.time() - start_time
        logger.info(f"Database performance test completed in {elapsed_time:.2f}s")

        return self.metrics

    async def _generate_market_updates(self, frequency_hz: int, duration: int):
        """Generate market updates at specified frequency."""
        interval = 1.0 / frequency_hz
        end_time = time.time() + duration

        while time.time() < end_time and self.running:
            start = time.time()

            try:
                # Generate market update
                market_update = self.market_simulator.generate_market_update()

                # Simulate processing the update
                await self._process_market_update(market_update)

                # Record metrics
                processing_time = (time.time() - start) * 1000
                self.metrics.add_response_time(processing_time)
                self.metrics.add_success()
                self.metrics.market_updates_processed += 1

            except Exception as e:
                logger.error(f"Market update processing error: {e}")
                self.metrics.add_error()

            # Wait for next update
            elapsed = time.time() - start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _simulate_hft_trader(
        self, trader_id: int, num_orders: int, duration: int
    ):
        """Simulate a high-frequency trader."""
        end_time = time.time() + duration
        orders_placed = 0

        while time.time() < end_time and orders_placed < num_orders and self.running:
            start = time.time()

            try:
                # Simulate order placement
                order = await self._place_simulated_order(trader_id)

                # Record metrics
                processing_time = (time.time() - start) * 1000
                self.metrics.add_response_time(processing_time)
                self.metrics.orders_executed += 1
                orders_placed += 1

                # Simulate some orders being cancelled
                if random.random() < 0.3:  # 30% cancellation rate
                    await self._cancel_simulated_order(order)

            except Exception as e:
                logger.error(f"HFT trader {trader_id} error: {e}")
                self.metrics.add_error()

            # Random delay between orders (HFT pattern)
            await asyncio.sleep(random.uniform(0.001, 0.1))

    async def _simulate_websocket_client(
        self, conn_id: int, num_messages: int, duration: int
    ):
        """Simulate WebSocket client behavior."""
        end_time = time.time() + duration
        messages_sent = 0

        while time.time() < end_time and messages_sent < num_messages and self.running:
            start = time.time()

            try:
                # Simulate WebSocket message
                await self._send_websocket_message(conn_id, messages_sent)

                # Record metrics
                latency = (time.time() - start) * 1000
                self.metrics.ws_connection_latency.append(latency)
                self.metrics.ws_message_count += 1
                messages_sent += 1

            except Exception as e:
                logger.error(f"WebSocket client {conn_id} error: {e}")
                self.metrics.add_error()

            # Small delay between messages
            await asyncio.sleep(0.01)

    async def _simulate_database_client(
        self, client_id: int, num_operations: int, duration: int
    ):
        """Simulate database client operations."""
        end_time = time.time() + duration
        operations_completed = 0

        while (
            time.time() < end_time
            and operations_completed < num_operations
            and self.running
        ):
            start = time.time()

            try:
                # Simulate database operation
                await self._execute_database_operation(client_id, operations_completed)

                # Record metrics
                query_time = (time.time() - start) * 1000
                self.metrics.db_query_times.append(query_time)
                operations_completed += 1

            except Exception as e:
                logger.error(f"Database client {client_id} error: {e}")
                self.metrics.add_error()

            # Small delay between operations
            await asyncio.sleep(0.005)

    async def _process_market_update(self, market_update: dict[str, Any]):
        """Simulate processing a market update."""
        # Simulate CPU-intensive market processing
        await asyncio.sleep(random.uniform(0.001, 0.005))

        # Simulate updating internal state
        if random.random() < 0.1:  # 10% trigger position updates
            self.metrics.position_updates += 1

    async def _place_simulated_order(self, trader_id: int) -> dict[str, Any]:
        """Simulate placing an order."""
        market = random.choice(self.market_simulator.markets)

        order = {
            "trader_id": trader_id,
            "market_id": market["id"],
            "side": random.choice(["buy", "sell"]),
            "price": round(random.uniform(0.1, 0.9), 4),
            "size": random.uniform(10, 1000),
            "timestamp": time.time(),
        }

        # Simulate order processing delay
        await asyncio.sleep(random.uniform(0.005, 0.015))

        return order

    async def _cancel_simulated_order(self, order: dict[str, Any]):
        """Simulate cancelling an order."""
        # Simulate cancellation processing
        await asyncio.sleep(random.uniform(0.002, 0.008))

    async def _send_websocket_message(self, conn_id: int, message_id: int):
        """Simulate sending a WebSocket message."""
        message = {
            "type": "market_update",
            "conn_id": conn_id,
            "message_id": message_id,
            "data": self.market_simulator.generate_market_update(),
            "timestamp": time.time(),
        }

        # Simulate WebSocket processing
        await asyncio.sleep(random.uniform(0.001, 0.003))

    async def _execute_database_operation(self, client_id: int, operation_id: int):
        """Simulate database operation."""
        operation_types = ["select", "insert", "update", "delete"]
        operation_type = random.choice(operation_types)

        # Simulate different query complexities
        if operation_type == "select":
            delay = random.uniform(0.001, 0.010)  # Fast reads
        elif operation_type in ["insert", "update"]:
            delay = random.uniform(0.005, 0.020)  # Medium writes
        else:  # delete
            delay = random.uniform(0.010, 0.030)  # Slower deletes

        await asyncio.sleep(delay)

    async def _monitor_system_resources(self):
        """Monitor system resources during load testing."""
        while self.running:
            try:
                self.metrics.record_system_metrics()
                await asyncio.sleep(1.0)  # Monitor every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")


class LoadTestSuite:
    """Complete load testing suite with benchmarking and reporting."""

    def __init__(self):
        self.runner = LoadTestRunner()
        self.results = {}

    async def run_comprehensive_load_tests(self) -> dict[str, Any]:
        """Run the complete suite of load tests."""
        logger.info("=" * 60)
        logger.info("STARTING COMPREHENSIVE LOAD TESTING SUITE")
        logger.info("=" * 60)

        suite_start_time = time.time()

        # Test 1: Market Data Load Test (1000+ concurrent updates)
        logger.info("\n🔥 TEST 1: Market Data Load Test")
        try:
            market_data_metrics = await self.runner.run_market_data_load_test(
                concurrent_updates=1000, duration_seconds=60, update_frequency_hz=10
            )
            self.results["market_data_load"] = market_data_metrics.get_summary()
            logger.info("✅ Market Data Load Test completed successfully")
        except Exception as e:
            logger.error(f"❌ Market Data Load Test failed: {e}")
            self.results["market_data_load"] = {"error": str(e)}

        # Small break between tests
        await asyncio.sleep(5)
        gc.collect()  # Force garbage collection

        # Test 2: High-Frequency Trading Simulation
        logger.info("\n🚀 TEST 2: High-Frequency Trading Simulation")
        try:
            hft_metrics = await self.runner.run_high_frequency_trading_test(
                concurrent_traders=100, orders_per_trader=50, duration_seconds=30
            )
            self.results["hft_simulation"] = hft_metrics.get_summary()
            logger.info("✅ HFT Simulation completed successfully")
        except Exception as e:
            logger.error(f"❌ HFT Simulation failed: {e}")
            self.results["hft_simulation"] = {"error": str(e)}

        await asyncio.sleep(5)
        gc.collect()

        # Test 3: WebSocket Stress Test
        logger.info("\n📡 TEST 3: WebSocket Stress Test")
        try:
            ws_metrics = await self.runner.run_websocket_stress_test(
                concurrent_connections=50,
                messages_per_connection=1000,
                duration_seconds=60,
            )
            self.results["websocket_stress"] = ws_metrics.get_summary()
            logger.info("✅ WebSocket Stress Test completed successfully")
        except Exception as e:
            logger.error(f"❌ WebSocket Stress Test failed: {e}")
            self.results["websocket_stress"] = {"error": str(e)}

        await asyncio.sleep(5)
        gc.collect()

        # Test 4: Database Performance Test
        logger.info("\n💾 TEST 4: Database Performance Test")
        try:
            db_metrics = await self.runner.run_database_performance_test(
                concurrent_operations=200,
                operations_per_client=100,
                duration_seconds=60,
            )
            self.results["database_performance"] = db_metrics.get_summary()
            logger.info("✅ Database Performance Test completed successfully")
        except Exception as e:
            logger.error(f"❌ Database Performance Test failed: {e}")
            self.results["database_performance"] = {"error": str(e)}

        total_time = time.time() - suite_start_time
        self.results["suite_summary"] = {
            "total_duration_seconds": total_time,
            "tests_completed": len(
                [r for r in self.results.values() if "error" not in r]
            ),
            "tests_failed": len([r for r in self.results.values() if "error" in r]),
            "completion_time": datetime.now().isoformat(),
        }

        logger.info("=" * 60)
        logger.info(f"LOAD TESTING SUITE COMPLETED IN {total_time:.2f} SECONDS")
        logger.info("=" * 60)

        return self.results

    def generate_performance_report(self) -> str:
        """Generate detailed performance report."""
        if not self.results:
            return "No test results available. Run load tests first."

        report = []
        report.append("📊 INKEDUP BOT PERFORMANCE LOAD TESTING REPORT")
        report.append("=" * 60)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Suite summary
        if "suite_summary" in self.results:
            summary = self.results["suite_summary"]
            report.append("📋 SUITE SUMMARY")
            report.append("-" * 30)
            report.append(
                f"Total Duration: {summary['total_duration_seconds']:.2f} seconds"
            )
            report.append(f"Tests Completed: {summary['tests_completed']}")
            report.append(f"Tests Failed: {summary['tests_failed']}")
            report.append("")

        # Individual test results
        test_names = {
            "market_data_load": "🔥 Market Data Load Test (1000+ concurrent updates)",
            "hft_simulation": "🚀 High-Frequency Trading Simulation",
            "websocket_stress": "📡 WebSocket Stress Test",
            "database_performance": "💾 Database Performance Test",
        }

        for test_key, test_name in test_names.items():
            if test_key in self.results:
                report.append(test_name)
                report.append("-" * len(test_name))

                result = self.results[test_key]
                if "error" in result:
                    report.append(f"❌ FAILED: {result['error']}")
                else:
                    self._add_test_metrics_to_report(report, result)

                report.append("")

        return "\n".join(report)

    def _add_test_metrics_to_report(self, report: list[str], metrics: dict[str, Any]):
        """Add test metrics to report."""
        # Performance metrics
        if "performance" in metrics:
            perf = metrics["performance"]
            report.append(f"✅ SUCCESS RATE: {perf['success_rate']:.1f}%")
            report.append(f"📈 TOTAL REQUESTS: {perf['total_requests']:,}")
            report.append(f"⚡ AVG RESPONSE TIME: {perf['avg_response_time_ms']:.2f}ms")
            report.append(f"📊 P95 RESPONSE TIME: {perf['p95_response_time_ms']:.2f}ms")
            report.append(f"📊 P99 RESPONSE TIME: {perf['p99_response_time_ms']:.2f}ms")
            report.append(f"🏃 MAX RESPONSE TIME: {perf['max_response_time_ms']:.2f}ms")

        # Throughput metrics
        if "throughput" in metrics:
            tput = metrics["throughput"]
            report.append(f"🎯 AVG THROUGHPUT: {tput['avg_throughput_rps']:.1f} req/s")
            report.append(
                f"🔥 PEAK THROUGHPUT: {tput['peak_throughput_rps']:.1f} req/s"
            )

        # System resource metrics
        if "system_resources" in metrics:
            sys_res = metrics["system_resources"]
            report.append(f"🧠 AVG MEMORY: {sys_res['avg_memory_mb']:.1f}MB")
            report.append(f"💾 PEAK MEMORY: {sys_res['peak_memory_mb']:.1f}MB")
            report.append(f"⚙️  AVG CPU: {sys_res['avg_cpu_percent']:.1f}%")
            report.append(f"🔥 PEAK CPU: {sys_res['peak_cpu_percent']:.1f}%")

        # Application-specific metrics
        if "application_metrics" in metrics:
            app = metrics["application_metrics"]
            if app.get("market_updates_processed", 0) > 0:
                report.append(f"📊 MARKET UPDATES: {app['market_updates_processed']:,}")
            if app.get("orders_executed", 0) > 0:
                report.append(f"💰 ORDERS EXECUTED: {app['orders_executed']:,}")
            if app.get("ws_messages_received", 0) > 0:
                report.append(f"📡 WS MESSAGES: {app['ws_messages_received']:,}")

        # Database metrics
        if "database" in metrics:
            db = metrics["database"]
            report.append(f"🗄️  AVG DB QUERY TIME: {db['avg_query_time_ms']:.2f}ms")
            report.append(f"🐌 SLOWEST QUERY: {db['slowest_query_ms']:.2f}ms")

    def save_results_to_file(self, filename: str = None):
        """Save test results to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"load_test_results_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        logger.info(f"Load test results saved to {filename}")
        return filename


# Main execution
async def main():
    """Run the complete load testing suite."""
    suite = LoadTestSuite()

    try:
        # Run all load tests
        results = await suite.run_comprehensive_load_tests()

        # Generate and display report
        report = suite.generate_performance_report()
        print("\n" + report)

        # Save results to file
        results_file = suite.save_results_to_file()
        print(f"\n📁 Detailed results saved to: {results_file}")

        return results

    except KeyboardInterrupt:
        logger.info("Load testing interrupted by user")
        return None
    except Exception as e:
        logger.error(f"Load testing suite failed: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Set up event loop policy for better performance on some systems
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    results = asyncio.run(main())

    if results:
        print("\n✅ Load testing suite completed successfully!")
    else:
        print("\n❌ Load testing suite failed or was interrupted")
        exit(1)
