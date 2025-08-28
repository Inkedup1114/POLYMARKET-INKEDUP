"""
Pytest configuration and fixtures for the InkedUp Polymarket Bot test suite.

This module provides shared fixtures and configuration for all tests,
including database setup, mock clients, and test utilities.
"""

import asyncio
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest import FixtureRequest

from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.enhanced_stub_client import StubClientConfig
from inkedup_bot.order_client import OrderClient
from inkedup_bot.risk.manager import RiskManager
from inkedup_bot.scanner import Scanner
from inkedup_bot.state import StateManager


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Provide a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "test.db"


@pytest.fixture
async def database_manager(temp_db_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Provide a database manager with a temporary database."""
    db = DatabaseManager(str(temp_db_path))
    await db.initialize()
    try:
        yield db
    finally:
        await db.close()


@pytest.fixture
async def state_manager(temp_db_path: Path) -> AsyncGenerator[StateManager, None]:
    """Provide a state manager with a temporary database."""
    state = StateManager(db_path=str(temp_db_path))
    await state.initialize_async()
    try:
        yield state
    finally:
        # Cleanup handled by state manager
        pass


@pytest.fixture
def test_config() -> BotConfig:
    """Provide a test configuration with safe defaults."""
    return BotConfig(
        # Use None for private_key to force stub client
        private_key=None,
        public_key="0x" + "0" * 40,  # Valid format but fake
        # Conservative risk settings for testing
        global_risk_cap=1000.0,
        max_position_size=100.0,
        max_market_exposure=250.0,
        # Fast settings for testing
        market_cache_ttl=5,
        book_cache_ttl=1,
        api_retry_attempts=1,  # Fail fast in tests
        # Strategy settings
        complement_arb_min_deviation=0.01,
        complement_arb_max_deviation=0.20,
        spread_alert_bps=50,
        # Logging
        log_level="DEBUG",
    )


@pytest.fixture
def stub_client_config() -> StubClientConfig:
    """Provide stub client configuration for testing."""
    return StubClientConfig(
        simulate_latency=False,  # Fast tests
        error_rate=0.0,  # No random errors in tests
        success_rate=1.0,  # Always succeed unless specifically testing failures
        default_response_delay=0.0,  # No artificial delays
    )


@pytest.fixture
async def order_client(
    test_config: BotConfig,
    state_manager: StateManager,
    stub_client_config: StubClientConfig,
) -> OrderClient:
    """Provide an order client configured for testing."""
    return OrderClient(test_config, state_manager, stub_client_config)


@pytest.fixture
async def risk_manager(
    test_config: BotConfig, order_client: OrderClient, state_manager: StateManager
) -> RiskManager:
    """Provide a risk manager configured for testing."""
    return RiskManager(test_config, order_client, state_manager)


@pytest.fixture
def mock_http_client() -> MagicMock:
    """Provide a mock HTTP client for testing."""
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.fixture
async def scanner(test_config: BotConfig, mock_http_client: MagicMock) -> Scanner:
    """Provide a scanner configured for testing."""
    scanner = Scanner(test_config)
    scanner.client = mock_http_client
    return scanner


@pytest.fixture
def sample_market_data() -> dict:
    """Provide sample market data for testing."""
    return {
        "slug": "test-market-1",
        "question": "Test Market Question?",
        "tokens": ["0xtoken1", "0xtoken2"],
        "token_ids": ["0xtoken1", "0xtoken2"],
        "active": True,
        "closed": False,
    }


@pytest.fixture
def sample_order_book() -> dict:
    """Provide sample order book data for testing."""
    return {
        "bids": [
            {"price": "0.55", "size": "100"},
            {"price": "0.54", "size": "200"},
        ],
        "asks": [
            {"price": "0.56", "size": "150"},
            {"price": "0.57", "size": "250"},
        ],
        "market": "0xmarket1",
        "token_id": "0xtoken1",
    }


@pytest.fixture
def sample_position_data() -> dict:
    """Provide sample position data for testing."""
    return {
        "token_id": "0xtoken1",
        "market_slug": "test-market",
        "outcome_type": "YES",
        "size": 100.0,
        "notional_value": 65.0,
    }


@pytest.fixture
def sample_order_data() -> dict:
    """Provide sample order data for testing."""
    return {
        "token_id": "0xtoken1",
        "side": "buy",
        "price": 0.65,
        "size": 100.0,
        "market_slug": "test-market",
        "outcome_type": "YES",
    }


# Performance test fixtures
@pytest.fixture
def performance_config() -> BotConfig:
    """Provide configuration optimized for performance testing."""
    return BotConfig(
        private_key=None,  # Stub client
        public_key="0x" + "0" * 40,
        # Higher limits for performance testing
        global_risk_cap=10000.0,
        max_position_size=1000.0,
        max_market_exposure=2500.0,
        # Performance settings
        market_cache_ttl=300,
        book_cache_ttl=30,
        book_batch_size=50,
        max_concurrent_requests=10,
        # Fast retries
        api_retry_attempts=3,
        api_retry_delay_seconds=0.1,
    )


# Integration test fixtures
@pytest.fixture(scope="session")
def integration_db_url() -> str:
    """Provide database URL for integration tests."""
    import os

    return os.getenv("DATABASE_URL", "sqlite:///test_integration.db")


@pytest.fixture
async def integration_database(
    integration_db_url: str,
) -> AsyncGenerator[DatabaseManager, None]:
    """Provide database for integration tests."""
    db = DatabaseManager(integration_db_url)
    await db.initialize()
    try:
        yield db
    finally:
        await db.close()


# Parametrize fixtures for different test scenarios
@pytest.fixture(params=["conservative", "moderate", "aggressive"])
def risk_config(request: FixtureRequest) -> BotConfig:
    """Provide different risk configurations for testing."""
    configs = {
        "conservative": BotConfig(
            private_key=None,
            public_key="0x" + "0" * 40,
            global_risk_cap=500.0,
            max_position_size=50.0,
            max_market_exposure=125.0,
            complement_arb_min_deviation=0.03,
        ),
        "moderate": BotConfig(
            private_key=None,
            public_key="0x" + "0" * 40,
            global_risk_cap=2500.0,
            max_position_size=250.0,
            max_market_exposure=625.0,
            complement_arb_min_deviation=0.02,
        ),
        "aggressive": BotConfig(
            private_key=None,
            public_key="0x" + "0" * 40,
            global_risk_cap=10000.0,
            max_position_size=1000.0,
            max_market_exposure=2500.0,
            complement_arb_min_deviation=0.01,
        ),
    }
    return configs[request.param]


# Async cleanup helper
@pytest.fixture(autouse=True)
async def cleanup_async_resources():
    """Automatically cleanup async resources after each test."""
    yield
    # Allow pending tasks to complete
    await asyncio.sleep(0.01)

    # Cancel any remaining tasks
    tasks = [t for t in asyncio.all_tasks() if not t.done()]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


# Pytest collection hooks
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Add 'unit' marker to all tests by default
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unit)

        # Mark tests based on file location
        if "test_integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "test_performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
        elif "test_load" in str(item.fspath):
            item.add_marker(pytest.mark.slow)

        # Mark async tests
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)


def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Register custom markers
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "performance: mark test as performance test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "unit: mark test as unit test")


# Test data generators
class TestDataFactory:
    """Factory for generating test data."""

    @staticmethod
    def create_market_data(slug: str = "test-market", active: bool = True) -> dict:
        """Create sample market data."""
        return {
            "slug": slug,
            "question": f"{slug.title()} Question?",
            "tokens": [f"0x{slug}token1", f"0x{slug}token2"],
            "token_ids": [f"0x{slug}token1", f"0x{slug}token2"],
            "active": active,
            "closed": not active,
        }

    @staticmethod
    def create_order_book(
        bid: float = 0.55, ask: float = 0.56, token_id: str = "0xtoken1"
    ) -> dict:
        """Create sample order book data."""
        return {
            "bids": [
                {"price": str(bid), "size": "100"},
                {"price": str(bid - 0.01), "size": "200"},
            ],
            "asks": [
                {"price": str(ask), "size": "150"},
                {"price": str(ask + 0.01), "size": "250"},
            ],
            "token_id": token_id,
        }


@pytest.fixture
def test_data_factory() -> TestDataFactory:
    """Provide test data factory."""
    return TestDataFactory()
