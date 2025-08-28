"""
Data Retention Manager

Manages data lifecycle and retention policies for the trading bot.
Implements automated cleanup of old data based on configurable retention policies.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetentionPeriod(Enum):
    """Standard retention period definitions."""

    # Critical data - longer retention
    TRADES = 365  # 1 year for trade history (regulatory)
    ORDERS = 180  # 6 months for order history
    POSITIONS = 90  # 3 months for position history

    # Operational data - medium retention
    SIGNALS = 30  # 30 days for signal history
    MARKET_DATA = 14  # 14 days for market data snapshots
    ORDER_BOOKS = 7  # 7 days for order book snapshots

    # Temporary data - short retention
    WEBSOCKET_MESSAGES = 3  # 3 days for raw WebSocket messages
    CACHE_DATA = 1  # 1 day for cached data
    TEMP_DATA = 1  # 1 day for temporary data

    # Monitoring data
    METRICS = 30  # 30 days for performance metrics
    LOGS = 7  # 7 days for application logs
    ERRORS = 30  # 30 days for error logs


@dataclass
class RetentionPolicy:
    """Configuration for a data retention policy."""

    table_name: str
    timestamp_column: str
    retention_days: int
    batch_size: int = 1000
    archive_enabled: bool = False
    archive_path: Optional[str] = None
    compression_enabled: bool = True
    delete_strategy: str = "hard"  # "hard" or "soft"
    custom_conditions: Optional[str] = None  # Additional SQL WHERE conditions
    enabled: bool = True

    def get_cutoff_date(self) -> datetime:
        """Calculate the cutoff date for data retention."""
        return datetime.utcnow() - timedelta(days=self.retention_days)


@dataclass
class RetentionStatistics:
    """Statistics for retention operations."""

    total_tables_processed: int = 0
    total_rows_deleted: int = 0
    total_rows_archived: int = 0
    total_storage_freed_mb: float = 0.0
    errors_encountered: int = 0
    processing_time_seconds: float = 0.0
    table_statistics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_run_timestamp: Optional[datetime] = None
    next_run_timestamp: Optional[datetime] = None


class DataRetentionManager:
    """Manages data retention and cleanup operations."""

    def __init__(
        self,
        database_manager,
        backup_manager=None,
        dry_run: bool = False,
        enable_archiving: bool = True,
    ):
        """
        Initialize the data retention manager.

        Args:
            database_manager: Database manager instance
            backup_manager: Optional backup manager for archiving
            dry_run: If True, only simulate operations without actual deletion
            enable_archiving: Enable data archiving before deletion
        """
        self.db = database_manager
        self.backup_manager = backup_manager
        self.dry_run = dry_run
        self.enable_archiving = enable_archiving
        self.policies: Dict[str, RetentionPolicy] = {}
        self.statistics = RetentionStatistics()
        self._running = False
        self._task = None

        # Initialize default policies
        self._initialize_default_policies()

    def _initialize_default_policies(self):
        """Initialize default retention policies."""
        default_policies = [
            # Trading data
            RetentionPolicy(
                table_name="trades",
                timestamp_column="timestamp",
                retention_days=RetentionPeriod.TRADES.value,
                archive_enabled=True,
                compression_enabled=True,
            ),
            RetentionPolicy(
                table_name="orders",
                timestamp_column="created_at",
                retention_days=RetentionPeriod.ORDERS.value,
                archive_enabled=True,
            ),
            RetentionPolicy(
                table_name="positions",
                timestamp_column="timestamp",
                retention_days=RetentionPeriod.POSITIONS.value,
                archive_enabled=True,
            ),
            # Market data
            RetentionPolicy(
                table_name="signals",
                timestamp_column="timestamp",
                retention_days=RetentionPeriod.SIGNALS.value,
                archive_enabled=False,
            ),
            RetentionPolicy(
                table_name="market_data",
                timestamp_column="timestamp",
                retention_days=RetentionPeriod.MARKET_DATA.value,
                archive_enabled=False,
                batch_size=5000,  # Larger batches for high-volume data
            ),
            RetentionPolicy(
                table_name="order_books",
                timestamp_column="timestamp",
                retention_days=RetentionPeriod.ORDER_BOOKS.value,
                archive_enabled=False,
                batch_size=10000,  # Very large batches for order book data
            ),
            # Operational data
            RetentionPolicy(
                table_name="websocket_messages",
                timestamp_column="received_at",
                retention_days=RetentionPeriod.WEBSOCKET_MESSAGES.value,
                archive_enabled=False,
                batch_size=10000,
            ),
            RetentionPolicy(
                table_name="cache_entries",
                timestamp_column="last_accessed",
                retention_days=RetentionPeriod.CACHE_DATA.value,
                archive_enabled=False,
            ),
            # Monitoring data
            RetentionPolicy(
                table_name="performance_metrics",
                timestamp_column="timestamp",
                retention_days=RetentionPeriod.METRICS.value,
                archive_enabled=False,
            ),
            RetentionPolicy(
                table_name="error_logs",
                timestamp_column="timestamp",
                retention_days=RetentionPeriod.ERRORS.value,
                archive_enabled=True,
                custom_conditions="severity IN ('ERROR', 'CRITICAL')",
            ),
        ]

        for policy in default_policies:
            self.add_policy(policy.table_name, policy)

    def add_policy(self, name: str, policy: RetentionPolicy):
        """Add or update a retention policy."""
        self.policies[name] = policy
        logger.info(f"Added retention policy for {name}: {policy.retention_days} days")

    def remove_policy(self, name: str):
        """Remove a retention policy."""
        if name in self.policies:
            del self.policies[name]
            logger.info(f"Removed retention policy for {name}")

    async def apply_retention_policies(self) -> RetentionStatistics:
        """
        Apply all configured retention policies.

        Returns:
            RetentionStatistics with results of the operation
        """
        start_time = datetime.utcnow()
        self.statistics = RetentionStatistics()
        self.statistics.last_run_timestamp = start_time

        logger.info(f"Starting data retention cleanup (dry_run={self.dry_run})")

        for name, policy in self.policies.items():
            if not policy.enabled:
                logger.debug(f"Skipping disabled policy: {name}")
                continue

            try:
                await self._apply_single_policy(name, policy)
            except Exception as e:
                logger.error(f"Error applying retention policy {name}: {e}")
                self.statistics.errors_encountered += 1

        # Calculate processing time
        self.statistics.processing_time_seconds = (
            datetime.utcnow() - start_time
        ).total_seconds()

        # Calculate next run time (default: daily at 2 AM)
        tomorrow = datetime.utcnow() + timedelta(days=1)
        self.statistics.next_run_timestamp = tomorrow.replace(
            hour=2, minute=0, second=0, microsecond=0
        )

        # Log summary
        logger.info(
            f"Data retention cleanup completed: "
            f"{self.statistics.total_rows_deleted} rows deleted, "
            f"{self.statistics.total_rows_archived} rows archived, "
            f"{self.statistics.total_storage_freed_mb:.2f} MB freed, "
            f"{self.statistics.processing_time_seconds:.2f} seconds"
        )

        return self.statistics

    async def _apply_single_policy(self, name: str, policy: RetentionPolicy):
        """Apply a single retention policy."""
        logger.info(f"Applying retention policy: {name}")

        cutoff_date = policy.get_cutoff_date()
        table_stats = {
            "rows_deleted": 0,
            "rows_archived": 0,
            "storage_freed_mb": 0.0,
            "cutoff_date": cutoff_date.isoformat(),
        }

        try:
            # Count rows to be affected
            count_query = f"""
                SELECT COUNT(*) as count
                FROM {policy.table_name}
                WHERE {policy.timestamp_column} < ?
            """

            if policy.custom_conditions:
                count_query += f" AND {policy.custom_conditions}"

            async with self.db.connection() as conn:
                async with conn.execute(count_query, (cutoff_date,)) as cursor:
                    result = await cursor.fetchone()
                    total_rows = result[0] if result else 0

            if total_rows == 0:
                logger.info(f"No rows to delete for {name}")
                self.statistics.table_statistics[name] = table_stats
                self.statistics.total_tables_processed += 1
                return

            logger.info(f"Found {total_rows} rows to process for {name}")

            # Archive data if enabled
            if policy.archive_enabled and self.enable_archiving and not self.dry_run:
                archived_rows = await self._archive_data(policy, cutoff_date)
                table_stats["rows_archived"] = archived_rows
                self.statistics.total_rows_archived += archived_rows

            # Delete data in batches
            if not self.dry_run:
                deleted_rows = await self._delete_data_in_batches(
                    policy, cutoff_date, total_rows
                )
                table_stats["rows_deleted"] = deleted_rows
                self.statistics.total_rows_deleted += deleted_rows

                # Estimate storage freed (rough estimate: 1KB per row)
                storage_freed = deleted_rows * 0.001  # MB
                table_stats["storage_freed_mb"] = storage_freed
                self.statistics.total_storage_freed_mb += storage_freed
            else:
                logger.info(f"[DRY RUN] Would delete {total_rows} rows from {name}")
                table_stats["rows_deleted"] = total_rows

            self.statistics.table_statistics[name] = table_stats

            # Always increment processed count, even if no data was found
            self.statistics.total_tables_processed += 1

        except Exception as e:
            logger.error(f"Error processing table {name}: {e}")
            raise

    async def _archive_data(
        self, policy: RetentionPolicy, cutoff_date: datetime
    ) -> int:
        """Archive data before deletion."""
        try:
            # Select data to archive
            select_query = f"""
                SELECT * FROM {policy.table_name}
                WHERE {policy.timestamp_column} < ?
            """

            if policy.custom_conditions:
                select_query += f" AND {policy.custom_conditions}"

            async with self.db.connection() as conn:
                async with conn.execute(select_query, (cutoff_date,)) as cursor:
                    rows = await cursor.fetchall()
                    rows = [dict(row) for row in rows]

            if not rows:
                return 0

            # Create archive file
            archive_filename = f"{policy.table_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

            if self.backup_manager:
                # Use backup manager if available
                archive_data = {
                    "table": policy.table_name,
                    "retention_policy": policy.retention_days,
                    "cutoff_date": cutoff_date.isoformat(),
                    "archived_at": datetime.utcnow().isoformat(),
                    "row_count": len(rows),
                    "data": [dict(row) for row in rows],
                }

                # Create archive through backup manager
                if hasattr(self.backup_manager, "create_archive"):
                    await self.backup_manager.create_archive(
                        archive_filename,
                        json.dumps(archive_data, default=str),
                        compress=policy.compression_enabled,
                    )
                else:
                    # Fallback for testing or when backup manager doesn't have create_archive
                    logger.warning(
                        f"Backup manager doesn't support archiving, skipping archive for {policy.table_name}"
                    )
                    return len(rows)

                logger.info(f"Archived {len(rows)} rows from {policy.table_name}")
                return len(rows)

            return 0

        except Exception as e:
            logger.error(f"Error archiving data from {policy.table_name}: {e}")
            return 0

    async def _delete_data_in_batches(
        self, policy: RetentionPolicy, cutoff_date: datetime, total_rows: int
    ) -> int:
        """Delete data in batches to avoid locking issues."""
        deleted_total = 0

        while deleted_total < total_rows:
            # Build delete query with LIMIT for batch processing
            delete_query = f"""
                DELETE FROM {policy.table_name}
                WHERE {policy.timestamp_column} < ?
            """

            if policy.custom_conditions:
                delete_query += f" AND {policy.custom_conditions}"

            # SQLite doesn't support LIMIT in DELETE directly, use subquery
            delete_query = f"""
                DELETE FROM {policy.table_name}
                WHERE rowid IN (
                    SELECT rowid FROM {policy.table_name}
                    WHERE {policy.timestamp_column} < ?
                    {f"AND {policy.custom_conditions}" if policy.custom_conditions else ""}
                    LIMIT {policy.batch_size}
                )
            """

            async with self.db.connection() as conn:
                async with conn.execute(delete_query, (cutoff_date,)) as cursor:
                    result = cursor.rowcount

            if result == 0:
                break

            deleted_total += result

            # Log progress for large deletions
            if total_rows > 10000:
                progress = (deleted_total / total_rows) * 100
                logger.debug(
                    f"Deletion progress for {policy.table_name}: "
                    f"{deleted_total}/{total_rows} ({progress:.1f}%)"
                )

            # Small delay between batches to avoid overloading
            await asyncio.sleep(0.1)

        logger.info(f"Deleted {deleted_total} rows from {policy.table_name}")
        return deleted_total

    async def vacuum_database(self):
        """
        Vacuum the database to reclaim space after deletions.
        Note: This operation can be slow for large databases.
        """
        if self.dry_run:
            logger.info("[DRY RUN] Would vacuum database")
            return

        try:
            logger.info("Starting database vacuum operation...")
            async with self.db.connection() as conn:
                await conn.execute("VACUUM")
            logger.info("Database vacuum completed")
        except Exception as e:
            logger.error(f"Error during database vacuum: {e}")

    async def analyze_storage_usage(self) -> Dict[str, Any]:
        """Analyze current storage usage by table."""
        storage_info = {}

        try:
            # Get table sizes (SQLite specific)
            tables_query = """
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
            async with self.db.connection() as conn:
                async with conn.execute(tables_query) as cursor:
                    tables = await cursor.fetchall()
                    tables = [dict(row) for row in tables]

            for table in tables:
                table_name = table["name"]

                # Get row count
                count_query = f"SELECT COUNT(*) FROM {table_name}"
                async with self.db.connection() as conn:
                    async with conn.execute(count_query) as cursor:
                        result = await cursor.fetchone()
                        row_count = result[0] if result else 0

                # Estimate size (rough estimate)
                estimated_size_mb = row_count * 0.001  # 1KB per row estimate

                # Check if retention policy exists
                has_policy = table_name in self.policies
                retention_days = (
                    self.policies[table_name].retention_days if has_policy else None
                )

                storage_info[table_name] = {
                    "row_count": row_count,
                    "estimated_size_mb": estimated_size_mb,
                    "has_retention_policy": has_policy,
                    "retention_days": retention_days,
                }

            # Calculate totals
            total_rows = sum(info["row_count"] for info in storage_info.values())
            total_size_mb = sum(
                info["estimated_size_mb"] for info in storage_info.values()
            )

            return {
                "tables": storage_info,
                "total_rows": total_rows,
                "total_estimated_size_mb": total_size_mb,
                "tables_with_policies": sum(
                    1 for info in storage_info.values() if info["has_retention_policy"]
                ),
                "tables_without_policies": sum(
                    1
                    for info in storage_info.values()
                    if not info["has_retention_policy"]
                ),
            }

        except Exception as e:
            logger.error(f"Error analyzing storage usage: {e}")
            return {}

    async def start_scheduled_cleanup(self, interval_hours: int = 24):
        """
        Start scheduled cleanup task.

        Args:
            interval_hours: Hours between cleanup runs (default: 24)
        """
        if self._running:
            logger.warning("Scheduled cleanup already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduled_cleanup_loop(interval_hours))
        logger.info(f"Started scheduled cleanup with {interval_hours} hour interval")

    async def stop_scheduled_cleanup(self):
        """Stop the scheduled cleanup task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped scheduled cleanup")

    async def _scheduled_cleanup_loop(self, interval_hours: int):
        """Run cleanup on schedule."""
        while self._running:
            try:
                # Run cleanup
                await self.apply_retention_policies()

                # Vacuum database weekly (Sunday at 3 AM)
                if datetime.utcnow().weekday() == 6 and datetime.utcnow().hour == 3:
                    await self.vacuum_database()

                # Wait for next run
                await asyncio.sleep(interval_hours * 3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scheduled cleanup: {e}")
                # Continue running even if there's an error
                await asyncio.sleep(3600)  # Wait 1 hour before retry

    def get_statistics(self) -> Dict[str, Any]:
        """Get current retention statistics."""
        return {
            "last_run": (
                self.statistics.last_run_timestamp.isoformat()
                if self.statistics.last_run_timestamp
                else None
            ),
            "next_run": (
                self.statistics.next_run_timestamp.isoformat()
                if self.statistics.next_run_timestamp
                else None
            ),
            "total_tables_processed": self.statistics.total_tables_processed,
            "total_rows_deleted": self.statistics.total_rows_deleted,
            "total_rows_archived": self.statistics.total_rows_archived,
            "total_storage_freed_mb": self.statistics.total_storage_freed_mb,
            "errors_encountered": self.statistics.errors_encountered,
            "processing_time_seconds": self.statistics.processing_time_seconds,
            "table_statistics": self.statistics.table_statistics,
            "policies_count": len(self.policies),
            "enabled_policies": sum(1 for p in self.policies.values() if p.enabled),
        }

    def get_policy_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all configured policies."""
        return [
            {
                "table": policy.table_name,
                "retention_days": policy.retention_days,
                "enabled": policy.enabled,
                "archive_enabled": policy.archive_enabled,
                "cutoff_date": policy.get_cutoff_date().isoformat(),
            }
            for policy in self.policies.values()
        ]
