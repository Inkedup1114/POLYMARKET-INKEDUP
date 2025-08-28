"""
Load testing for the InkedUp Polymarket Bot using Locust.

This module provides load testing scenarios to validate system performance
under various load conditions and identify bottlenecks.
"""

import random
import time

from locust import HttpUser, TaskSet, between, task
from locust.env import Environment


class TradingBotUser(HttpUser):
    """Simulates a trading bot user for load testing."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    host = "http://localhost:8080"  # Default host

    def on_start(self):
        """Initialize user session."""
        self.client.verify = False  # Disable SSL verification for testing
        self.market_slugs = [
            "test-market-1",
            "test-market-2",
            "test-market-3",
            "election-2024",
            "crypto-price",
        ]
        self.token_ids = [
            "0x" + "1" * 40,
            "0x" + "2" * 40,
            "0x" + "3" * 40,
            "0x" + "4" * 40,
        ]

    @task(3)
    def get_markets(self):
        """Test market data fetching - most common operation."""
        response = self.client.get("/api/markets", name="get_markets")
        if response.status_code == 200:
            try:
                data = response.json()
                assert isinstance(data, list), "Markets should be a list"
            except ValueError:
                self.client.events.request_failure.fire(
                    request_type="GET",
                    name="get_markets",
                    response_time=response.elapsed.total_seconds() * 1000,
                    response_length=len(response.content),
                    exception="Invalid JSON response",
                )

    @task(2)
    def get_order_book(self):
        """Test order book fetching."""
        token_id = random.choice(self.token_ids)
        response = self.client.get(f"/api/books/{token_id}", name="get_order_book")
        if response.status_code == 200:
            try:
                data = response.json()
                assert "bids" in data and "asks" in data
            except (ValueError, AssertionError) as e:
                self.client.events.request_failure.fire(
                    request_type="GET",
                    name="get_order_book",
                    response_time=response.elapsed.total_seconds() * 1000,
                    response_length=len(response.content),
                    exception=str(e),
                )

    @task(1)
    def place_order(self):
        """Test order placement - resource intensive operation."""
        order_data = {
            "token_id": random.choice(self.token_ids),
            "side": random.choice(["buy", "sell"]),
            "price": round(random.uniform(0.1, 0.9), 2),
            "size": round(random.uniform(10, 100), 1),
            "market_slug": random.choice(self.market_slugs),
        }

        response = self.client.post("/api/orders", json=order_data, name="place_order")

        # Order placement should either succeed or fail with proper error
        if response.status_code not in [200, 201, 400, 403]:
            self.client.events.request_failure.fire(
                request_type="POST",
                name="place_order",
                response_time=response.elapsed.total_seconds() * 1000,
                response_length=len(response.content),
                exception=f"Unexpected status code: {response.status_code}",
            )

    @task(1)
    def get_positions(self):
        """Test position retrieval."""
        response = self.client.get("/api/positions", name="get_positions")
        if response.status_code == 200:
            try:
                data = response.json()
                assert isinstance(data, list), "Positions should be a list"
            except (ValueError, AssertionError) as e:
                self.client.events.request_failure.fire(
                    request_type="GET",
                    name="get_positions",
                    response_time=response.elapsed.total_seconds() * 1000,
                    response_length=len(response.content),
                    exception=str(e),
                )

    @task(1)
    def get_risk_metrics(self):
        """Test risk metrics retrieval."""
        response = self.client.get("/api/risk/metrics", name="get_risk_metrics")
        if response.status_code == 200:
            try:
                data = response.json()
                assert "total_exposure" in data
                assert "utilization" in data
            except (ValueError, AssertionError) as e:
                self.client.events.request_failure.fire(
                    request_type="GET",
                    name="get_risk_metrics",
                    response_time=response.elapsed.total_seconds() * 1000,
                    response_length=len(response.content),
                    exception=str(e),
                )


class ScannerTaskSet(TaskSet):
    """Task set focusing on market scanning operations."""

    @task(5)
    def scan_markets(self):
        """Simulate market scanning."""
        response = self.client.get(
            "/api/scan", params={"top": random.randint(5, 20)}, name="scan_markets"
        )

        if response.status_code == 200:
            try:
                data = response.json()
                assert isinstance(data, list)
                # Validate scan results structure
                for item in data[:3]:  # Check first few items
                    assert "slug" in item
                    assert "tokens" in item
            except (ValueError, AssertionError) as e:
                self.client.events.request_failure.fire(
                    request_type="GET",
                    name="scan_markets",
                    response_time=response.elapsed.total_seconds() * 1000,
                    response_length=len(response.content),
                    exception=str(e),
                )

    @task(2)
    def get_arbitrage_opportunities(self):
        """Check for arbitrage opportunities."""
        response = self.client.get(
            "/api/opportunities/arbitrage", name="get_arbitrage_opportunities"
        )

        if response.status_code == 200:
            try:
                data = response.json()
                assert isinstance(data, list)
            except (ValueError, AssertionError) as e:
                self.client.events.request_failure.fire(
                    request_type="GET",
                    name="get_arbitrage_opportunities",
                    response_time=response.elapsed.total_seconds() * 1000,
                    response_length=len(response.content),
                    exception=str(e),
                )


class HighVolumeUser(TradingBotUser):
    """Simulates high-volume trading user."""

    wait_time = between(0.1, 0.5)  # Much faster requests
    weight = 1

    @task(10)
    def rapid_market_checks(self):
        """Rapid market data requests."""
        market_slug = random.choice(self.market_slugs)
        response = self.client.get(
            f"/api/markets/{market_slug}", name="rapid_market_check"
        )

        # Track response times for SLA monitoring
        if response.elapsed.total_seconds() > 1.0:
            self.client.events.request_failure.fire(
                request_type="GET",
                name="rapid_market_check",
                response_time=response.elapsed.total_seconds() * 1000,
                response_length=len(response.content),
                exception="Response time > 1s SLA violation",
            )


class WebSocketUser(HttpUser):
    """Simulates WebSocket connections for real-time data."""

    wait_time = between(5, 15)  # Longer waits for persistent connections

    def on_start(self):
        """Initialize WebSocket connection."""
        self.ws_connected = False
        # Note: Actual WebSocket testing would require websocket library
        # This simulates the connection overhead
        time.sleep(0.1)  # Simulate connection time
        self.ws_connected = True

    @task(1)
    def simulate_ws_message(self):
        """Simulate processing WebSocket messages."""
        if not self.ws_connected:
            return

        # Simulate receiving and processing real-time updates
        start_time = time.time()

        # Simulate message processing time
        time.sleep(random.uniform(0.001, 0.01))

        processing_time = (time.time() - start_time) * 1000

        # Track processing performance
        self.client.events.request_success.fire(
            request_type="WebSocket",
            name="process_market_update",
            response_time=processing_time,
            response_length=100,  # Approximate message size
        )


# Load testing scenarios
class MarketDataLoadTest:
    """Market data focused load test."""

    @staticmethod
    def run_test():
        """Run market data load test."""
        env = Environment(user_classes=[TradingBotUser])
        env.create_local_runner()

        # Start load test
        env.runner.start(user_count=10, spawn_rate=2)

        # Run for 60 seconds
        time.sleep(60)

        env.runner.quit()
        return env.stats


class HighVolumeLoadTest:
    """High volume trading load test."""

    @staticmethod
    def run_test():
        """Run high volume load test."""
        env = Environment(user_classes=[HighVolumeUser])
        env.create_local_runner()

        # More aggressive load
        env.runner.start(user_count=50, spawn_rate=5)

        # Run for 120 seconds
        time.sleep(120)

        env.runner.quit()
        return env.stats


class MixedWorkloadTest:
    """Mixed workload simulating real usage patterns."""

    @staticmethod
    def run_test():
        """Run mixed workload test."""
        env = Environment(
            user_classes=[
                (TradingBotUser, 3),  # 60% normal users
                (HighVolumeUser, 1),  # 20% high volume users
                (WebSocketUser, 1),  # 20% WebSocket users
            ]
        )
        env.create_local_runner()

        # Realistic mixed load
        env.runner.start(user_count=25, spawn_rate=1)

        # Run for 180 seconds (3 minutes)
        time.sleep(180)

        env.runner.quit()
        return env.stats


# Stress test scenarios
class StressTestUser(HttpUser):
    """Stress test user with no wait time."""

    wait_time = between(0, 0.1)  # Minimal wait

    def on_start(self):
        """Initialize stress test user."""
        self.error_count = 0
        self.request_count = 0

    @task
    def stress_endpoint(self):
        """Stress test critical endpoints."""
        self.request_count += 1

        endpoints = [
            "/api/markets",
            "/api/scan",
            "/api/positions",
            "/api/risk/metrics",
        ]

        endpoint = random.choice(endpoints)
        response = self.client.get(endpoint, name="stress_test")

        if response.status_code >= 400:
            self.error_count += 1

        # Track error rate
        error_rate = self.error_count / self.request_count
        if error_rate > 0.05:  # More than 5% errors
            self.client.events.request_failure.fire(
                request_type="GET",
                name="stress_test",
                response_time=response.elapsed.total_seconds() * 1000,
                response_length=len(response.content),
                exception=f"Error rate too high: {error_rate:.2%}",
            )


def run_stress_test():
    """Run stress test to find breaking points."""
    env = Environment(user_classes=[StressTestUser])
    env.create_local_runner()

    print("Starting stress test...")

    # Gradually increase load
    for user_count in [10, 25, 50, 100, 200]:
        print(f"Testing with {user_count} users...")
        env.runner.start(user_count=user_count, spawn_rate=10)
        time.sleep(30)  # Test for 30 seconds at each level

        # Check if system is still responding
        stats = env.runner.stats
        if stats.total.avg_response_time > 5000:  # 5 second average
            print(f"System degraded at {user_count} users")
            break
        if stats.total.fail_ratio > 0.1:  # More than 10% failures
            print(f"High failure rate at {user_count} users")
            break

    env.runner.quit()
    return env.stats


# Performance benchmarking
class BenchmarkUser(HttpUser):
    """User class for performance benchmarking."""

    wait_time = between(1, 2)

    @task
    def benchmark_scan(self):
        """Benchmark market scanning performance."""
        start_time = time.time()

        response = self.client.get("/api/scan?top=50", name="benchmark_scan")

        if response.status_code == 200:
            duration = time.time() - start_time

            # Log performance metrics
            print(f"Scan completed in {duration:.3f}s")

            # Performance thresholds
            if duration > 2.0:
                self.client.events.request_failure.fire(
                    request_type="GET",
                    name="benchmark_scan",
                    response_time=duration * 1000,
                    response_length=len(response.content),
                    exception=f"Scan too slow: {duration:.3f}s",
                )


if __name__ == "__main__":
    # Run different test scenarios
    print("Running load tests...")

    # Quick smoke test
    print("\n1. Market Data Load Test")
    MarketDataLoadTest.run_test()

    print("\n2. High Volume Load Test")
    HighVolumeLoadTest.run_test()

    print("\n3. Mixed Workload Test")
    MixedWorkloadTest.run_test()

    print("\n4. Stress Test")
    run_stress_test()

    print("\nLoad testing completed!")
