import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest

from inkedup_bot.database import DatabaseManager


@pytest.fixture
async def db_manager() -> AsyncGenerator[DatabaseManager, None]:
    """Fixture to set up and tear down a test database."""
    db_path = Path("test_bot_data.db")
    db = DatabaseManager(db_path=db_path)
    await db.initialize()

    yield db

    # Teardown: close connection and remove the database file
    await asyncio.sleep(0.1)  # allow db to close
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_insert_and_get_order(db_manager: DatabaseManager) -> None:
    """Verify that data can be written to and read from the database."""
    order_id = str(uuid4())
    order_data = {
        "id": order_id,
        "token_id": "0x123",
        "market_slug": "test-market",
        "side": "buy",
        "price": 0.5,
        "size": 100,
        "status": "OPEN",
        "notional_value": 50.0,
        "outcome_type": "YES",
    }

    await db_manager.insert_order(order_data)
    retrieved_order = await db_manager.get_order(order_id)

    assert retrieved_order is not None
    assert retrieved_order["id"] == order_id
    assert retrieved_order["status"] == "OPEN"


@pytest.mark.asyncio
async def test_update_order(db_manager: DatabaseManager) -> None:
    """Verify that data can be updated in the database."""
    order_id = str(uuid4())
    order_data = {
        "id": order_id,
        "token_id": "0x123",
        "market_slug": "test-market",
        "side": "buy",
        "price": 0.5,
        "size": 100,
        "status": "OPEN",
        "notional_value": 50.0,
        "outcome_type": "YES",
    }
    await db_manager.insert_order(order_data)

    update_data = {"status": "FILLED"}
    await db_manager.update_order(order_id, update_data)

    updated_order = await db_manager.get_order(order_id)
    assert updated_order is not None
    assert updated_order["status"] == "FILLED"


@pytest.mark.asyncio
async def test_delete_order_as_cancelled(db_manager: DatabaseManager) -> None:
    """Verify that an order can be 'deleted' (marked as CANCELLED)."""
    order_id = str(uuid4())
    order_data = {
        "id": order_id,
        "token_id": "0x123",
        "market_slug": "test-market",
        "side": "buy",
        "price": 0.5,
        "size": 100,
        "status": "OPEN",
        "notional_value": 50.0,
        "outcome_type": "YES",
    }
    await db_manager.insert_order(order_data)

    # In this system, "deleting" an order means cancelling it
    await db_manager.update_order(order_id, {"status": "CANCELLED"})

    cancelled_order = await db_manager.get_order(order_id)
    assert cancelled_order is not None
    assert cancelled_order["status"] == "CANCELLED"

    # also check that it's not considered an "open" order
    open_orders = await db_manager.get_open_orders()
    assert order_id not in [o["id"] for o in open_orders]


@pytest.mark.asyncio
async def test_insert_and_retrieve_trade(db_manager: DatabaseManager) -> None:
    """Test inserting and retrieving trade records."""
    order_id = str(uuid4())
    trade_data = {
        "order_id": order_id,
        "token_id": "0x123",
        "market_slug": "test-market",
        "side": "buy",
        "price": 0.5,
        "size": 100,
        "notional_value": 50.0,
        "outcome_type": "YES",
    }

    await db_manager.insert_trade(trade_data)

    # Verify trade was inserted by checking via SQL
    async with db_manager.connection() as db:
        cursor = await db.execute(
            "SELECT * FROM trades WHERE order_id = ?", (order_id,)
        )
        trade = await cursor.fetchone()
        assert trade is not None
        assert dict(trade)["order_id"] == order_id


@pytest.mark.asyncio
async def test_position_operations(db_manager: DatabaseManager) -> None:
    """Test position insertion, update, and retrieval."""
    token_id = "0x123"
    position_data = {
        "token_id": token_id,
        "market_slug": "test-market",
        "outcome_type": "YES",
        "size": 100.0,
        "notional_value": 50.0,
    }

    # Insert position
    await db_manager.upsert_position(position_data)

    # Retrieve position
    position = await db_manager.get_position(token_id)
    assert position is not None
    assert position["token_id"] == token_id
    assert position["size"] == 100.0

    # Update position (upsert)
    updated_data = {
        "token_id": token_id,
        "market_slug": "test-market",
        "outcome_type": "YES",
        "size": 150.0,
        "notional_value": 75.0,
    }
    await db_manager.upsert_position(updated_data)

    # Verify update
    updated_position = await db_manager.get_position(token_id)
    assert updated_position is not None, "Position not found after upsert."
    assert updated_position["size"] == 150.0
    assert updated_position["notional_value"] == 75.0


@pytest.mark.asyncio
async def test_market_snapshot_operations(db_manager: DatabaseManager) -> None:
    """Test market snapshot insertion and cleanup."""
    snapshot_data = {
        "market_slug": "test-market",
        "token_id": "0x123",
        "bid": 0.45,
        "ask": 0.55,
        "spread_bps": 200.0,
        "volume_24h": 1000.0,
        "liquidity": 5000.0,
    }

    await db_manager.insert_market_snapshot(snapshot_data)

    # Verify insertion
    async with db_manager.connection() as db:
        cursor = await db.execute(
            "SELECT * FROM market_snapshots WHERE market_slug = ? AND token_id = ?",
            (snapshot_data["market_slug"], snapshot_data["token_id"]),
        )
        snapshot = await cursor.fetchone()
        assert snapshot is not None
        assert dict(snapshot)["bid"] == 0.45


@pytest.mark.asyncio
async def test_risk_event_logging(db_manager: DatabaseManager) -> None:
    """Test risk event logging."""
    event_data = {
        "event_type": "POSITION_LIMIT_BREACH",
        "token_id": "0x123",
        "market_slug": "test-market",
        "outcome_type": "YES",
        "current_exposure": 150.0,
        "limit_value": 100.0,
        "intended_notional": 75.0,
        "description": "Position limit exceeded",
    }

    await db_manager.log_risk_event(event_data)

    # Verify insertion
    async with db_manager.connection() as db:
        cursor = await db.execute(
            "SELECT * FROM risk_events WHERE event_type = ?",
            (event_data["event_type"],),
        )
        event = await cursor.fetchone()
        assert event is not None
        assert dict(event)["current_exposure"] == 150.0


@pytest.mark.asyncio
async def test_exposure_calculations(db_manager: DatabaseManager) -> None:
    """Test exposure calculation methods."""
    # Insert test positions
    positions = [
        {
            "token_id": "0x123",
            "market_slug": "market-1",
            "outcome_type": "YES",
            "size": 100.0,
            "notional_value": 50.0,
        },
        {
            "token_id": "0x456",
            "market_slug": "market-1",
            "outcome_type": "NO",
            "size": -50.0,
            "notional_value": -25.0,
        },
        {
            "token_id": "0x789",
            "market_slug": "market-2",
            "outcome_type": "YES",
            "size": 75.0,
            "notional_value": 37.5,
        },
    ]

    for pos in positions:
        await db_manager.upsert_position(pos)

    # Test total exposure
    total_exposure = await db_manager.get_total_exposure()
    assert total_exposure == 112.5  # sum of abs values: 50 + 25 + 37.5

    # Test market-specific exposure
    market1_exposure = await db_manager.get_market_exposure("market-1")
    assert market1_exposure == 75.0  # 50 + 25

    # Test outcome-specific exposure
    yes_exposure = await db_manager.get_outcome_exposure("YES")
    assert yes_exposure == 87.5  # 50 + 37.5

    # Test position notional
    pos_notional = await db_manager.get_position_notional("0x123")
    assert pos_notional == 50.0


@pytest.mark.asyncio
async def test_get_open_orders(db_manager: DatabaseManager) -> None:
    """Test getting open orders filtering."""
    orders = [
        {
            "id": "order1",
            "token_id": "0x123",
            "side": "buy",
            "price": 0.5,
            "size": 100,
            "status": "OPEN",
            "notional_value": 50.0,
        },
        {
            "id": "order2",
            "token_id": "0x456",
            "side": "sell",
            "price": 0.6,
            "size": 100,
            "status": "FILLED",
            "notional_value": 60.0,
        },
        {
            "id": "order3",
            "token_id": "0x789",
            "side": "buy",
            "price": 0.4,
            "size": 100,
            "status": "CANCELLED",
            "notional_value": 40.0,
        },
        {
            "id": "order4",
            "token_id": "0xabc",
            "side": "sell",
            "price": 0.7,
            "size": 100,
            "status": "PENDING",
            "notional_value": 70.0,
        },
    ]

    for order in orders:
        await db_manager.insert_order(order)

    open_orders = await db_manager.get_open_orders()
    open_order_ids = [o["id"] for o in open_orders]

    # Should only include OPEN and PENDING orders
    assert "order1" in open_order_ids
    assert "order4" in open_order_ids
    assert "order2" not in open_order_ids  # FILLED
    assert "order3" not in open_order_ids  # CANCELLED


@pytest.mark.asyncio
async def test_snapshot_cleanup(db_manager: DatabaseManager) -> None:
    """Test snapshot cleanup functionality."""
    # Insert old snapshot via raw SQL to control timestamp
    async with db_manager.connection() as db:
        await db.execute(
            """
            INSERT INTO market_snapshots
            (market_slug, token_id, bid, ask, snapshot_at)
            VALUES (?, ?, ?, ?, datetime('now', '-10 days'))
            """,
            ("old-market", "0x123", 0.4, 0.6),
        )
        await db.commit()

    # Insert recent snapshot
    recent_data = {
        "market_slug": "new-market",
        "token_id": "0x456",
        "bid": 0.5,
        "ask": 0.7,
    }
    await db_manager.insert_market_snapshot(recent_data)

    # Cleanup snapshots older than 7 days
    await db_manager.cleanup_old_snapshots(days_to_keep=7)

    # Verify old snapshot was removed and recent one remains
    async with db_manager.connection() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM market_snapshots")
        count = await cursor.fetchone()
        assert count[0] == 1  # Only recent snapshot should remain

        cursor = await db.execute("SELECT market_slug FROM market_snapshots")
        remaining = await cursor.fetchone()
        assert dict(remaining) is not None
        assert remaining[0] == "new-market"


@pytest.mark.asyncio
async def test_database_initialization_idempotent(db_manager: DatabaseManager) -> None:
    """Test that database initialization is idempotent."""
    # Initialize again - should not fail
    await db_manager.initialize()
    assert db_manager._initialized is True

    # Verify tables still exist and work
    test_order = {
        "id": str(uuid4()),
        "token_id": "0x123",
        "side": "buy",
        "price": 0.5,
        "size": 100,
        "status": "OPEN",
        "notional_value": 50.0,
    }
    await db_manager.insert_order(test_order)
    retrieved = await db_manager.get_order(test_order["id"])
    assert retrieved is not None


@pytest.mark.asyncio
async def test_database_cleanup(db_manager: DatabaseManager) -> None:
    """Ensure that the tests clean up after themselves."""
    # This test just uses the fixture, and success is determined
    # by the fixture's teardown logic running without error.
    # We can add an assertion to make it explicit.
    assert db_manager.db_path.exists()
