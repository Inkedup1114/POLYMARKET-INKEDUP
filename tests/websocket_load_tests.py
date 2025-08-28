#!/usr/bin/env python3
"""
WebSocket Load Testing for InkedUp Bot

This module specifically tests WebSocket performance under high-frequency
trading conditions with realistic market data streams and connection management.
"""

import asyncio
import json
import logging
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

import psutil
import websockets

logger = logging.getLogger("websocket_load_tests")


@dataclass
class WebSocketMetrics:
    """WebSocket-specific performance metrics."""

    connection_times: list[float] = field(default_factory=list)
    message_latencies: list[float] = field(default_factory=list)
    messages_sent: int = 0
    messages_received: int = 0
    connection_failures: int = 0
    message_failures: int = 0
    reconnections: int = 0
    throughput_per_second: list[float] = field(default_factory=list)
    memory_usage: list[float] = field(default_factory=list)

    def add_connection_time(self, time_ms: float):
        """Record connection establishment time."""
        self.connection_times.append(time_ms)

    def add_message_latency(self, latency_ms: float):
        """Record message round-trip latency."""
        self.message_latencies.append(latency_ms)

    def record_throughput(self, messages_per_second: float):
        """Record throughput measurement."""
        self.throughput_per_second.append(messages_per_second)

    def record_memory_usage(self):
        """Record current memory usage."""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.memory_usage.append(memory_mb)

    def get_summary(self) -> dict[str, Any]:
        """Generate comprehensive WebSocket metrics summary."""
        return {
            "connections": {
                "total_attempts": len(self.connection_times) + self.connection_failures,
                "successful_connections": len(self.connection_times),
                "connection_failure_rate": (
                    self.connection_failures
                    / (len(self.connection_times) + self.connection_failures)
                    * 100
                    if (len(self.connection_times) + self.connection_failures) > 0
                    else 0
                ),
                "avg_connection_time_ms": (
                    statistics.mean(self.connection_times)
                    if self.connection_times
                    else 0
                ),
                "max_connection_time_ms": (
                    max(self.connection_times) if self.connection_times else 0
                ),
                "reconnections": self.reconnections,
            },
            "messaging": {
                "messages_sent": self.messages_sent,
                "messages_received": self.messages_received,
                "message_loss_rate": (
                    (self.messages_sent - self.messages_received)
                    / self.messages_sent
                    * 100
                    if self.messages_sent > 0
                    else 0
                ),
                "message_failure_rate": (
                    self.message_failures
                    / (self.messages_sent + self.message_failures)
                    * 100
                    if (self.messages_sent + self.message_failures) > 0
                    else 0
                ),
                "avg_latency_ms": (
                    statistics.mean(self.message_latencies)
                    if self.message_latencies
                    else 0
                ),
                "p95_latency_ms": self._percentile(self.message_latencies, 95),
                "p99_latency_ms": self._percentile(self.message_latencies, 99),
                "max_latency_ms": (
                    max(self.message_latencies) if self.message_latencies else 0
                ),
            },
            "throughput": {
                "avg_messages_per_second": (
                    statistics.mean(self.throughput_per_second)
                    if self.throughput_per_second
                    else 0
                ),
                "peak_messages_per_second": (
                    max(self.throughput_per_second) if self.throughput_per_second else 0
                ),
            },
            "resources": {
                "avg_memory_mb": (
                    statistics.mean(self.memory_usage) if self.memory_usage else 0
                ),
                "peak_memory_mb": max(self.memory_usage) if self.memory_usage else 0,
            },
        }

    def _percentile(self, data: list[float], percentile: float) -> float:
        """Calculate percentile value."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]


class MockWebSocketServer:
    """Mock WebSocket server for load testing."""

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.server = None
        self.clients = set()
        self.message_count = 0

    async def start_server(self):
        """Start the mock WebSocket server."""
        self.server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            max_size=2**20,  # 1MB max message size
            max_queue=100,  # Max queued messages per connection
        )
        logger.info(f"Mock WebSocket server started on ws://{self.host}:{self.port}")

        # Start market data broadcast
        asyncio.create_task(self.broadcast_market_data())

    async def stop_server(self):
        """Stop the mock WebSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Mock WebSocket server stopped")

    async def handle_client(self, websocket, path):
        """Handle individual client connections."""
        self.clients.add(websocket)
        client_id = len(self.clients)

        logger.debug(f"Client {client_id} connected from {websocket.remote_address}")

        try:
            # Send welcome message
            await websocket.send(
                json.dumps(
                    {
                        "type": "welcome",
                        "client_id": client_id,
                        "timestamp": time.time(),
                    }
                )
            )

            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.process_client_message(websocket, data, client_id)
                except json.JSONDecodeError:
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "error",
                                "message": "Invalid JSON",
                                "timestamp": time.time(),
                            }
                        )
                    )

        except websockets.exceptions.ConnectionClosed:
            logger.debug(f"Client {client_id} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            self.clients.discard(websocket)

    async def process_client_message(
        self, websocket, data: dict[str, Any], client_id: int
    ):
        """Process messages from clients."""
        message_type = data.get("type", "unknown")

        if message_type == "ping":
            # Respond to ping with pong
            await websocket.send(
                json.dumps(
                    {
                        "type": "pong",
                        "client_id": client_id,
                        "original_timestamp": data.get("timestamp", time.time()),
                        "server_timestamp": time.time(),
                    }
                )
            )

        elif message_type == "subscribe":
            # Handle subscription requests
            await websocket.send(
                json.dumps(
                    {
                        "type": "subscription_ack",
                        "client_id": client_id,
                        "subscribed_to": data.get("channels", []),
                        "timestamp": time.time(),
                    }
                )
            )

        elif message_type == "order":
            # Simulate order processing
            await asyncio.sleep(
                random.uniform(0.001, 0.01)
            )  # Simulate processing delay
            await websocket.send(
                json.dumps(
                    {
                        "type": "order_ack",
                        "order_id": data.get(
                            "order_id", f"order_{client_id}_{time.time()}"
                        ),
                        "status": "filled" if random.random() > 0.1 else "partial",
                        "client_id": client_id,
                        "timestamp": time.time(),
                    }
                )
            )

    async def broadcast_market_data(self):
        """Broadcast market data to all connected clients."""
        while True:
            if self.clients:
                market_data = self.generate_market_data()

                # Broadcast to all clients
                disconnected = set()
                for websocket in self.clients.copy():
                    try:
                        await websocket.send(json.dumps(market_data))
                        self.message_count += 1
                    except websockets.exceptions.ConnectionClosed:
                        disconnected.add(websocket)
                    except Exception as e:
                        logger.error(f"Broadcast error: {e}")
                        disconnected.add(websocket)

                # Clean up disconnected clients
                for websocket in disconnected:
                    self.clients.discard(websocket)

            # Broadcast at 10Hz (100ms intervals)
            await asyncio.sleep(0.1)

    def generate_market_data(self) -> dict[str, Any]:
        """Generate realistic market data."""
        return {
            "type": "market_data",
            "market_id": f"market_{random.randint(1, 100)}",
            "yes_price": round(random.uniform(0.1, 0.9), 4),
            "no_price": round(random.uniform(0.1, 0.9), 4),
            "volume": random.randint(1000, 100000),
            "timestamp": time.time(),
            "sequence": self.message_count,
        }


class WebSocketLoadTester:
    """Main WebSocket load testing class."""

    def __init__(self):
        self.metrics = WebSocketMetrics()
        self.server = None

    async def setup_test_server(self):
        """Set up mock WebSocket server for testing."""
        self.server = MockWebSocketServer()
        await self.server.start_server()
        # Give server a moment to start
        await asyncio.sleep(0.5)

    async def teardown_test_server(self):
        """Tear down test server."""
        if self.server:
            await self.server.stop_server()

    async def test_connection_scalability(
        self,
        max_connections: int = 1000,
        connection_rate: int = 50,
        hold_time_seconds: int = 30,
    ) -> dict[str, Any]:
        """
        Test WebSocket connection scalability.

        Args:
            max_connections: Maximum concurrent connections to establish
            connection_rate: Connections per second to establish
            hold_time_seconds: How long to hold connections open
        """
        logger.info(
            f"🔗 Testing connection scalability: {max_connections} connections at {connection_rate}/s"
        )

        self.metrics = WebSocketMetrics()
        connections = []
        connection_tasks = []

        async def establish_connection(conn_id: int):
            """Establish a single WebSocket connection."""
            try:
                connect_start = time.time()

                websocket = await websockets.connect(
                    f"ws://{self.server.host}:{self.server.port}",
                    max_size=2**20,
                    ping_interval=None,  # Disable automatic pings for testing
                )

                connect_time = (time.time() - connect_start) * 1000
                self.metrics.add_connection_time(connect_time)
                connections.append(websocket)

                # Hold connection for specified time
                await asyncio.sleep(hold_time_seconds)

                await websocket.close()

            except Exception as e:
                logger.error(f"Connection {conn_id} failed: {e}")
                self.metrics.connection_failures += 1

        # Establish connections at specified rate
        for i in range(max_connections):
            task = asyncio.create_task(establish_connection(i))
            connection_tasks.append(task)

            # Rate limiting for connection establishment
            if (i + 1) % connection_rate == 0:
                await asyncio.sleep(1.0)

        # Wait for all connections to complete
        await asyncio.gather(*connection_tasks, return_exceptions=True)

        summary = self.metrics.get_summary()
        summary["test_parameters"] = {
            "max_connections": max_connections,
            "connection_rate": connection_rate,
            "hold_time_seconds": hold_time_seconds,
        }

        logger.info(
            f"✅ Connection scalability test completed: "
            f"{summary['connections']['successful_connections']}/{max_connections} successful"
        )

        return summary

    async def test_message_throughput(
        self,
        concurrent_clients: int = 100,
        messages_per_client: int = 1000,
        message_rate_hz: int = 10,
    ) -> dict[str, Any]:
        """
        Test message throughput under high-frequency conditions.

        Args:
            concurrent_clients: Number of concurrent WebSocket clients
            messages_per_client: Messages each client should send
            message_rate_hz: Messages per second per client
        """
        logger.info(
            f"📡 Testing message throughput: {concurrent_clients} clients, "
            f"{messages_per_client} messages each at {message_rate_hz} Hz"
        )

        self.metrics = WebSocketMetrics()

        async def run_client(client_id: int):
            """Run a single WebSocket client for throughput testing."""
            try:
                websocket = await websockets.connect(
                    f"ws://{self.server.host}:{self.server.port}"
                )

                messages_sent = 0
                start_time = time.time()
                message_interval = 1.0 / message_rate_hz

                # Send messages at specified rate
                while messages_sent < messages_per_client:
                    message_start = time.time()

                    # Send ping message for latency measurement
                    message = {
                        "type": "ping",
                        "client_id": client_id,
                        "message_id": messages_sent,
                        "timestamp": time.time(),
                    }

                    await websocket.send(json.dumps(message))
                    self.metrics.messages_sent += 1
                    messages_sent += 1

                    # Listen for response (non-blocking)
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        response_data = json.loads(response)

                        if response_data.get("type") == "pong":
                            latency = (
                                time.time() - response_data.get("original_timestamp", 0)
                            ) * 1000
                            self.metrics.add_message_latency(latency)
                            self.metrics.messages_received += 1

                    except TimeoutError:
                        pass  # No response received, continue
                    except json.JSONDecodeError:
                        self.metrics.message_failures += 1

                    # Rate limiting
                    elapsed = time.time() - message_start
                    sleep_time = max(0, message_interval - elapsed)
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)

                await websocket.close()

                # Calculate client throughput
                total_time = time.time() - start_time
                client_throughput = messages_sent / total_time
                self.metrics.record_throughput(client_throughput)

            except Exception as e:
                logger.error(f"Client {client_id} error: {e}")
                self.metrics.connection_failures += 1

        # Start all clients concurrently
        client_tasks = [run_client(i) for i in range(concurrent_clients)]

        # Monitor memory usage during test
        monitor_task = asyncio.create_task(self._monitor_memory())

        start_time = time.time()
        await asyncio.gather(*client_tasks, return_exceptions=True)
        total_time = time.time() - start_time

        monitor_task.cancel()

        summary = self.metrics.get_summary()
        summary["test_parameters"] = {
            "concurrent_clients": concurrent_clients,
            "messages_per_client": messages_per_client,
            "target_rate_hz": message_rate_hz,
            "actual_duration_seconds": total_time,
        }
        summary["overall_throughput"] = {
            "total_messages": self.metrics.messages_sent,
            "messages_per_second": (
                self.metrics.messages_sent / total_time if total_time > 0 else 0
            ),
        }

        logger.info(
            f"✅ Message throughput test completed: "
            f"{self.metrics.messages_sent} messages in {total_time:.2f}s"
        )

        return summary

    async def test_connection_resilience(
        self,
        concurrent_clients: int = 50,
        reconnection_interval: float = 5.0,
        test_duration_seconds: int = 60,
    ) -> dict[str, Any]:
        """
        Test WebSocket connection resilience with disconnections and reconnections.

        Args:
            concurrent_clients: Number of concurrent clients
            reconnection_interval: Seconds between forced reconnections
            test_duration_seconds: Total test duration
        """
        logger.info(
            f"🔄 Testing connection resilience: {concurrent_clients} clients, "
            f"reconnecting every {reconnection_interval}s for {test_duration_seconds}s"
        )

        self.metrics = WebSocketMetrics()

        async def resilient_client(client_id: int):
            """Run a client that handles disconnections and reconnections."""
            end_time = time.time() + test_duration_seconds
            reconnect_count = 0

            while time.time() < end_time:
                try:
                    connect_start = time.time()
                    websocket = await websockets.connect(
                        f"ws://{self.server.host}:{self.server.port}"
                    )

                    connect_time = (time.time() - connect_start) * 1000
                    self.metrics.add_connection_time(connect_time)

                    if reconnect_count > 0:
                        self.metrics.reconnections += 1

                    # Send messages while connected
                    connection_start = time.time()
                    message_count = 0

                    while (
                        time.time() - connection_start
                    ) < reconnection_interval and time.time() < end_time:
                        try:
                            message = {
                                "type": "ping",
                                "client_id": client_id,
                                "reconnect_count": reconnect_count,
                                "message_count": message_count,
                                "timestamp": time.time(),
                            }

                            await websocket.send(json.dumps(message))
                            self.metrics.messages_sent += 1
                            message_count += 1

                            # Try to receive response
                            try:
                                response = await asyncio.wait_for(
                                    websocket.recv(), timeout=0.1
                                )
                                self.metrics.messages_received += 1
                            except TimeoutError:
                                pass

                            await asyncio.sleep(0.1)  # Send at 10Hz

                        except websockets.exceptions.ConnectionClosed:
                            break
                        except Exception as e:
                            logger.debug(f"Client {client_id} message error: {e}")
                            self.metrics.message_failures += 1

                    await websocket.close()
                    reconnect_count += 1

                    # Brief pause before reconnecting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(f"Client {client_id} connection error: {e}")
                    self.metrics.connection_failures += 1
                    reconnect_count += 1
                    await asyncio.sleep(1.0)  # Wait longer after connection failure

        # Start resilient clients
        client_tasks = [resilient_client(i) for i in range(concurrent_clients)]

        # Monitor memory usage during test
        monitor_task = asyncio.create_task(self._monitor_memory())

        await asyncio.gather(*client_tasks, return_exceptions=True)

        monitor_task.cancel()

        summary = self.metrics.get_summary()
        summary["test_parameters"] = {
            "concurrent_clients": concurrent_clients,
            "reconnection_interval": reconnection_interval,
            "test_duration_seconds": test_duration_seconds,
        }

        logger.info(
            f"✅ Connection resilience test completed: "
            f"{self.metrics.reconnections} reconnections"
        )

        return summary

    async def _monitor_memory(self):
        """Monitor memory usage during WebSocket tests."""
        while True:
            try:
                self.metrics.record_memory_usage()
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break


async def run_websocket_load_tests():
    """Run comprehensive WebSocket load testing suite."""
    logger.info("🌐 Starting WebSocket Load Testing Suite")
    logger.info("=" * 60)

    tester = WebSocketLoadTester()
    results = {}

    try:
        # Set up test server
        await tester.setup_test_server()

        # Test 1: Connection Scalability
        logger.info("\n🔗 TEST 1: Connection Scalability")
        try:
            scalability_results = await tester.test_connection_scalability(
                max_connections=500, connection_rate=50, hold_time_seconds=10
            )
            results["connection_scalability"] = scalability_results
        except Exception as e:
            logger.error(f"Connection scalability test failed: {e}")
            results["connection_scalability"] = {"error": str(e)}

        await asyncio.sleep(2)  # Brief pause between tests

        # Test 2: Message Throughput
        logger.info("\n📡 TEST 2: Message Throughput")
        try:
            throughput_results = await tester.test_message_throughput(
                concurrent_clients=100, messages_per_client=100, message_rate_hz=10
            )
            results["message_throughput"] = throughput_results
        except Exception as e:
            logger.error(f"Message throughput test failed: {e}")
            results["message_throughput"] = {"error": str(e)}

        await asyncio.sleep(2)

        # Test 3: Connection Resilience
        logger.info("\n🔄 TEST 3: Connection Resilience")
        try:
            resilience_results = await tester.test_connection_resilience(
                concurrent_clients=25,
                reconnection_interval=3.0,
                test_duration_seconds=30,
            )
            results["connection_resilience"] = resilience_results
        except Exception as e:
            logger.error(f"Connection resilience test failed: {e}")
            results["connection_resilience"] = {"error": str(e)}

    finally:
        await tester.teardown_test_server()

    logger.info("\n" + "=" * 60)
    logger.info("🏁 WebSocket Load Testing Suite Completed")
    logger.info("=" * 60)

    return results


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    # Run WebSocket load tests
    results = asyncio.run(run_websocket_load_tests())

    if results:
        print("\n📡 WEBSOCKET LOAD TEST RESULTS:")
        print("=" * 50)

        for test_name, result in results.items():
            print(f"\n📊 {test_name.upper().replace('_', ' ')}:")
            if "error" in result:
                print(f"  ❌ FAILED: {result['error']}")
            else:
                # Print key metrics
                if "connections" in result:
                    conn = result["connections"]
                    print(
                        f"  🔗 Successful Connections: {conn['successful_connections']}"
                    )
                    print(
                        f"  🔗 Connection Failure Rate: {conn['connection_failure_rate']:.2f}%"
                    )
                    print(
                        f"  🔗 Avg Connection Time: {conn['avg_connection_time_ms']:.2f}ms"
                    )

                if "messaging" in result:
                    msg = result["messaging"]
                    print(f"  📨 Messages Sent: {msg['messages_sent']}")
                    print(f"  📨 Message Loss Rate: {msg['message_loss_rate']:.2f}%")
                    print(f"  📨 Avg Latency: {msg['avg_latency_ms']:.2f}ms")
                    print(f"  📨 P99 Latency: {msg['p99_latency_ms']:.2f}ms")

                if "throughput" in result:
                    tput = result["throughput"]
                    print(
                        f"  🚀 Avg Throughput: {tput['avg_messages_per_second']:.1f} msg/s"
                    )
                    print(
                        f"  🚀 Peak Throughput: {tput['peak_messages_per_second']:.1f} msg/s"
                    )

        print("\n✅ WebSocket load testing completed!")
    else:
        print("\n❌ WebSocket load testing failed!")
        exit(1)
