"""
Test Data Retention Manager
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from inkedup_bot.data_retention import (
    DataRetentionManager,
    RetentionPeriod,
    RetentionPolicy,
    RetentionStatistics,
)


@pytest.fixture
def mock_database():
    """Create a mock database manager."""
    db = Mock()
    db.fetch_one = AsyncMock()
    db.fetch_all = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def mock_backup_manager():
    """Create a mock backup manager."""
    backup = Mock()
    backup.create_archive = AsyncMock()
    return backup


@pytest.fixture
def retention_manager(mock_database, mock_backup_manager):
    """Create a retention manager with mocked dependencies."""
    return DataRetentionManager(
        database_manager=mock_database,
        backup_manager=mock_backup_manager,
        dry_run=False,
        enable_archiving=True,
    )


class TestRetentionPolicy:
    """Test RetentionPolicy dataclass."""

    def test_retention_policy_creation(self):
        """Test creating a retention policy."""
        policy = RetentionPolicy(
            table_name="test_table",
            timestamp_column="created_at",
            retention_days=30,
            batch_size=1000,
            archive_enabled=True,
        )

        assert policy.table_name == "test_table"
        assert policy.timestamp_column == "created_at"
        assert policy.retention_days == 30
        assert policy.batch_size == 1000
        assert policy.archive_enabled is True
        assert policy.enabled is True

    def test_get_cutoff_date(self):
        """Test calculating cutoff date."""
        policy = RetentionPolicy(
            table_name="test_table", timestamp_column="created_at", retention_days=7
        )

        cutoff = policy.get_cutoff_date()
        expected = datetime.utcnow() - timedelta(days=7)

        # Allow 1 second tolerance for test execution time
        assert abs((cutoff - expected).total_seconds()) < 1


class TestDataRetentionManager:
    """Test DataRetentionManager class."""

    def test_initialization(self, retention_manager):
        """Test retention manager initialization."""
        assert retention_manager.dry_run is False
        assert retention_manager.enable_archiving is True
        assert len(retention_manager.policies) > 0  # Default policies loaded
        assert retention_manager._running is False

    def test_default_policies(self, retention_manager):
        """Test that default policies are loaded."""
        # Check some key default policies exist
        assert "trades" in retention_manager.policies
        assert "orders" in retention_manager.policies
        assert "positions" in retention_manager.policies
        assert "signals" in retention_manager.policies

        # Verify retention periods
        trades_policy = retention_manager.policies["trades"]
        assert trades_policy.retention_days == RetentionPeriod.TRADES.value
        assert trades_policy.archive_enabled is True

    def test_add_policy(self, retention_manager):
        """Test adding a custom policy."""
        custom_policy = RetentionPolicy(
            table_name="custom_table", timestamp_column="timestamp", retention_days=14
        )

        retention_manager.add_policy("custom", custom_policy)

        assert "custom" in retention_manager.policies
        assert retention_manager.policies["custom"].table_name == "custom_table"

    def test_remove_policy(self, retention_manager):
        """Test removing a policy."""
        # Add a policy first
        retention_manager.add_policy(
            "test",
            RetentionPolicy(
                table_name="test", timestamp_column="timestamp", retention_days=1
            ),
        )

        assert "test" in retention_manager.policies

        # Remove it
        retention_manager.remove_policy("test")
        assert "test" not in retention_manager.policies

    @pytest.mark.asyncio
    async def test_apply_retention_policies_no_data(
        self, retention_manager, mock_database
    ):
        """Test applying policies when no data needs deletion."""
        # Mock no rows to delete
        mock_database.fetch_one.return_value = {"count": 0}

        stats = await retention_manager.apply_retention_policies()

        assert stats.total_rows_deleted == 0
        assert stats.total_rows_archived == 0
        assert stats.errors_encountered == 0
        assert stats.total_tables_processed > 0

    @pytest.mark.asyncio
    async def test_apply_retention_policies_with_data(
        self, retention_manager, mock_database
    ):
        """Test applying policies with data to delete."""
        # Mock data to delete
        mock_database.fetch_one.return_value = {"count": 100}
        mock_database.execute.return_value = 100  # Deleted rows

        # Only test with one policy for simplicity
        retention_manager.policies = {
            "test": RetentionPolicy(
                table_name="test_table",
                timestamp_column="created_at",
                retention_days=7,
                archive_enabled=False,  # Skip archiving for this test
            )
        }

        stats = await retention_manager.apply_retention_policies()

        assert stats.total_rows_deleted == 100
        assert stats.total_tables_processed == 1
        assert stats.errors_encountered == 0
        assert "test" in stats.table_statistics

    @pytest.mark.asyncio
    async def test_apply_retention_policies_with_archiving(
        self, retention_manager, mock_database, mock_backup_manager
    ):
        """Test applying policies with archiving enabled."""
        # Mock data to archive and delete
        mock_database.fetch_one.return_value = {"count": 2}
        mock_database.fetch_all.return_value = [
            {"id": 1, "data": "test1"},
            {"id": 2, "data": "test2"},
        ]
        mock_database.execute.return_value = 2

        # Single policy with archiving
        retention_manager.policies = {
            "test": RetentionPolicy(
                table_name="test_table",
                timestamp_column="created_at",
                retention_days=7,
                archive_enabled=True,
            )
        }

        stats = await retention_manager.apply_retention_policies()

        # Verify archiving was called
        mock_backup_manager.create_archive.assert_called_once()
        assert stats.total_rows_archived == 2
        assert stats.total_rows_deleted == 2

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, mock_database):
        """Test dry run mode doesn't delete data."""
        # Create manager in dry run mode
        manager = DataRetentionManager(database_manager=mock_database, dry_run=True)

        mock_database.fetch_one.return_value = {"count": 100}

        # Single policy for testing
        manager.policies = {
            "test": RetentionPolicy(
                table_name="test_table", timestamp_column="created_at", retention_days=7
            )
        }

        stats = await manager.apply_retention_policies()

        # In dry run, execute should not be called
        mock_database.execute.assert_not_called()

        # Stats should show what would be deleted
        assert "test" in stats.table_statistics
        assert stats.table_statistics["test"]["rows_deleted"] == 100

    @pytest.mark.asyncio
    async def test_vacuum_database(self, retention_manager, mock_database):
        """Test database vacuum operation."""
        await retention_manager.vacuum_database()

        mock_database.execute.assert_called_once_with("VACUUM")

    @pytest.mark.asyncio
    async def test_vacuum_database_dry_run(self, mock_database):
        """Test vacuum in dry run mode."""
        manager = DataRetentionManager(database_manager=mock_database, dry_run=True)

        await manager.vacuum_database()

        # Should not execute vacuum in dry run
        mock_database.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_storage_usage(self, retention_manager, mock_database):
        """Test analyzing storage usage."""
        # Mock table list
        mock_database.fetch_all.return_value = [
            {"name": "trades"},
            {"name": "orders"},
            {"name": "signals"},
        ]

        # Mock row counts
        mock_database.fetch_one.side_effect = [
            {"count": 1000},  # trades
            {"count": 500},  # orders
            {"count": 2000},  # signals
        ]

        storage_info = await retention_manager.analyze_storage_usage()

        assert storage_info["total_rows"] == 3500
        assert storage_info["total_estimated_size_mb"] == 3.5  # 1KB per row estimate
        assert len(storage_info["tables"]) == 3
        assert storage_info["tables"]["trades"]["row_count"] == 1000

    @pytest.mark.asyncio
    async def test_scheduled_cleanup_start_stop(self, retention_manager):
        """Test starting and stopping scheduled cleanup."""
        # Start scheduled cleanup
        await retention_manager.start_scheduled_cleanup(interval_hours=1)

        assert retention_manager._running is True
        assert retention_manager._task is not None

        # Stop scheduled cleanup
        await retention_manager.stop_scheduled_cleanup()

        assert retention_manager._running is False

    def test_get_statistics(self, retention_manager):
        """Test getting retention statistics."""
        # Set some test statistics
        retention_manager.statistics.total_rows_deleted = 100
        retention_manager.statistics.total_rows_archived = 50
        retention_manager.statistics.total_tables_processed = 5

        stats = retention_manager.get_statistics()

        assert stats["total_rows_deleted"] == 100
        assert stats["total_rows_archived"] == 50
        assert stats["total_tables_processed"] == 5
        assert stats["policies_count"] > 0

    def test_get_policy_summary(self, retention_manager):
        """Test getting policy summary."""
        summary = retention_manager.get_policy_summary()

        assert len(summary) > 0

        # Check structure of summary items
        for item in summary:
            assert "table" in item
            assert "retention_days" in item
            assert "enabled" in item
            assert "archive_enabled" in item
            assert "cutoff_date" in item

    @pytest.mark.asyncio
    async def test_batch_deletion(self, retention_manager, mock_database):
        """Test that large deletions are done in batches."""
        # Mock a large number of rows
        mock_database.fetch_one.return_value = {"count": 5000}

        # Mock batch deletions
        mock_database.execute.side_effect = [1000, 1000, 1000, 1000, 1000, 0]

        policy = RetentionPolicy(
            table_name="test_table",
            timestamp_column="created_at",
            retention_days=7,
            batch_size=1000,
            archive_enabled=False,
        )

        retention_manager.policies = {"test": policy}

        stats = await retention_manager.apply_retention_policies()

        # Should have made multiple delete calls
        assert mock_database.execute.call_count >= 5
        assert stats.total_rows_deleted == 5000

    @pytest.mark.asyncio
    async def test_error_handling(self, retention_manager, mock_database):
        """Test error handling during retention operations."""
        # Mock an error
        mock_database.fetch_one.side_effect = Exception("Database error")

        stats = await retention_manager.apply_retention_policies()

        # Should handle errors gracefully
        assert stats.errors_encountered > 0
        assert stats.total_rows_deleted == 0


class TestRetentionPeriod:
    """Test RetentionPeriod enum."""

    def test_retention_periods(self):
        """Test retention period values."""
        assert RetentionPeriod.TRADES.value == 365
        assert RetentionPeriod.ORDERS.value == 180
        assert RetentionPeriod.POSITIONS.value == 90
        assert RetentionPeriod.SIGNALS.value == 30
        assert RetentionPeriod.MARKET_DATA.value == 14
        assert RetentionPeriod.ORDER_BOOKS.value == 7
        assert RetentionPeriod.WEBSOCKET_MESSAGES.value == 3
        assert RetentionPeriod.CACHE_DATA.value == 1
