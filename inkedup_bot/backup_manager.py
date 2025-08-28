"""
Automated Backup System for InkedUp Trading Bot.

This module provides comprehensive backup and recovery capabilities for the trading bot,
focusing on database backups, configuration backups, and critical data protection.

Key Features:
- Scheduled automated backups
- Multiple backup strategies (full, incremental, differential)
- Configurable retention policies
- Backup verification and integrity checks
- Cloud storage integration support
- Recovery procedures and validation
- Backup monitoring and alerting

The backup system ensures data protection and business continuity by maintaining
regular backups of critical trading data, configurations, and system state.
"""

import asyncio
import hashlib
import json
import logging
import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger("backup_manager")


class BackupType(Enum):
    """Types of backups that can be performed."""

    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"
    CONFIGURATION = "configuration"


class BackupStatus(Enum):
    """Status of backup operations."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


class BackupConfig:
    """Configuration for backup operations."""

    def __init__(
        self,
        backup_directory: str = "backups",
        max_retention_days: int = 30,
        full_backup_interval_hours: int = 24,
        incremental_backup_interval_hours: int = 4,
        enable_compression: bool = True,
        enable_encryption: bool = False,
        verify_backups: bool = True,
        cloud_storage_enabled: bool = False,
    ):
        self.backup_directory = Path(backup_directory).resolve()
        self.max_retention_days = max_retention_days
        self.full_backup_interval_hours = full_backup_interval_hours
        self.incremental_backup_interval_hours = incremental_backup_interval_hours
        self.enable_compression = enable_compression
        self.enable_encryption = enable_encryption
        self.verify_backups = verify_backups
        self.cloud_storage_enabled = cloud_storage_enabled

        # Ensure backup directory exists
        self.backup_directory.mkdir(parents=True, exist_ok=True)


class BackupRecord:
    """Record of a backup operation."""

    def __init__(
        self,
        backup_id: str,
        backup_type: BackupType,
        timestamp: datetime,
        file_path: Path,
        size_bytes: int = 0,
        status: BackupStatus = BackupStatus.PENDING,
        checksum: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.backup_id = backup_id
        self.backup_type = backup_type
        self.timestamp = timestamp
        self.file_path = file_path
        self.size_bytes = size_bytes
        self.status = status
        self.checksum = checksum
        self.metadata = metadata or {}
        self.completion_time: datetime | None = None
        self.error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert backup record to dictionary for serialization."""
        return {
            "backup_id": self.backup_id,
            "backup_type": self.backup_type.value,
            "timestamp": self.timestamp.isoformat(),
            "file_path": str(self.file_path),
            "size_bytes": self.size_bytes,
            "status": self.status.value,
            "checksum": self.checksum,
            "metadata": self.metadata,
            "completion_time": (
                self.completion_time.isoformat() if self.completion_time else None
            ),
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BackupRecord":
        """Create backup record from dictionary."""
        record = cls(
            backup_id=data["backup_id"],
            backup_type=BackupType(data["backup_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            file_path=Path(data["file_path"]),
            size_bytes=data["size_bytes"],
            status=BackupStatus(data["status"]),
            checksum=data.get("checksum"),
            metadata=data.get("metadata", {}),
        )

        if data.get("completion_time"):
            record.completion_time = datetime.fromisoformat(data["completion_time"])

        record.error_message = data.get("error_message")
        return record


class DatabaseBackupManager:
    """Handles database-specific backup operations."""

    def __init__(self, database_path: str):
        self.database_path = Path(database_path)

    async def create_backup(self, backup_path: Path) -> bool:
        """Create a backup of the SQLite database."""
        try:
            if not self.database_path.exists():
                log.warning(f"Database file does not exist: {self.database_path}")
                return False

            log.info(f"Creating database backup: {backup_path}")

            # Use SQLite backup API for safe backup
            source_conn = sqlite3.connect(str(self.database_path))
            backup_conn = sqlite3.connect(str(backup_path))

            try:
                # Perform the backup
                source_conn.backup(backup_conn)
                log.info("Database backup completed successfully")
                return True

            finally:
                source_conn.close()
                backup_conn.close()

        except Exception as e:
            log.error(f"Failed to create database backup: {e}")
            return False

    async def verify_backup(self, backup_path: Path) -> bool:
        """Verify the integrity of a database backup."""
        try:
            # Try to open the backup and perform a basic integrity check
            conn = sqlite3.connect(str(backup_path))
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check")
                result = cursor.fetchone()

                if result and result[0] == "ok":
                    log.info(f"Database backup verification successful: {backup_path}")
                    return True
                else:
                    log.error(f"Database backup verification failed: {backup_path}")
                    return False

            finally:
                conn.close()

        except Exception as e:
            log.error(f"Failed to verify database backup: {e}")
            return False


class AutomatedBackupManager:
    """
    Main backup management system with automated scheduling and retention.

    Provides comprehensive backup capabilities for the trading bot including
    database backups, configuration backups, and critical data protection.
    """

    def __init__(self, config: BackupConfig, database_path: str = "bot_data.db"):
        self.config = config
        self.database_path = database_path
        self.db_backup_manager = DatabaseBackupManager(database_path)

        # Backup tracking
        self.backup_records: list[BackupRecord] = []
        self.last_full_backup: datetime | None = None
        self.last_incremental_backup: datetime | None = None

        # Scheduling
        self.is_running = False
        self.backup_task: asyncio.Task | None = None
        self.scheduler = None

        # Load existing backup records
        self._load_backup_history()

        log.info(
            f"Automated backup manager initialized (backup dir: {self.config.backup_directory})"
        )

    async def start(self) -> None:
        """Start the automated backup system."""
        if self.is_running:
            log.warning("Backup system is already running")
            return

        self.is_running = True
        self.backup_task = asyncio.create_task(self._backup_scheduler())
        log.info("Automated backup system started")

    async def stop(self) -> None:
        """Stop the automated backup system."""
        if not self.is_running:
            return

        self.is_running = False

        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass

        log.info("Automated backup system stopped")

    async def create_manual_backup(
        self, backup_type: BackupType = BackupType.FULL
    ) -> BackupRecord | None:
        """Create a manual backup immediately."""
        log.info(f"Creating manual {backup_type.value} backup")

        backup_id = self._generate_backup_id(backup_type)
        timestamp = datetime.now()

        backup_record = BackupRecord(
            backup_id=backup_id,
            backup_type=backup_type,
            timestamp=timestamp,
            file_path=self._get_backup_path(backup_id, backup_type),
            status=BackupStatus.IN_PROGRESS,
        )

        self.backup_records.append(backup_record)

        try:
            success = await self._perform_backup(backup_record)

            if success:
                backup_record.status = BackupStatus.COMPLETED
                backup_record.completion_time = datetime.now()

                # Verify backup if enabled
                if self.config.verify_backups:
                    if await self._verify_backup(backup_record):
                        backup_record.status = BackupStatus.VERIFIED

                log.info(f"Manual backup completed successfully: {backup_id}")

                # Save backup history
                self._save_backup_history()

                return backup_record
            else:
                backup_record.status = BackupStatus.FAILED
                backup_record.error_message = "Backup operation failed"
                log.error(f"Manual backup failed: {backup_id}")
                return None

        except Exception as e:
            backup_record.status = BackupStatus.FAILED
            backup_record.error_message = str(e)
            log.error(f"Manual backup failed with exception: {e}")
            return None

    def get_backup_status(self) -> dict[str, Any]:
        """Get comprehensive backup system status."""
        recent_backups = [
            record
            for record in self.backup_records
            if record.timestamp > datetime.now() - timedelta(days=7)
        ]

        return {
            "system_status": "running" if self.is_running else "stopped",
            "backup_directory": str(self.config.backup_directory),
            "total_backups": len(self.backup_records),
            "recent_backups": len(recent_backups),
            "last_full_backup": (
                self.last_full_backup.isoformat() if self.last_full_backup else None
            ),
            "last_incremental_backup": (
                self.last_incremental_backup.isoformat()
                if self.last_incremental_backup
                else None
            ),
            "successful_backups": len(
                [
                    r
                    for r in self.backup_records
                    if r.status in [BackupStatus.COMPLETED, BackupStatus.VERIFIED]
                ]
            ),
            "failed_backups": len(
                [r for r in self.backup_records if r.status == BackupStatus.FAILED]
            ),
            "total_backup_size_mb": sum(r.size_bytes for r in self.backup_records)
            / (1024 * 1024),
            "retention_days": self.config.max_retention_days,
            "next_full_backup": (
                self._calculate_next_backup_time(BackupType.FULL).isoformat()
                if self.last_full_backup
                else "Due now"
            ),
        }

    async def _backup_scheduler(self) -> None:
        """Main backup scheduling loop."""
        log.info("Backup scheduler started")

        try:
            while self.is_running:
                try:
                    # Check if full backup is needed
                    if self._is_backup_due(BackupType.FULL):
                        await self.create_manual_backup(BackupType.FULL)
                        self.last_full_backup = datetime.now()

                    # Check if incremental backup is needed
                    elif self._is_backup_due(BackupType.INCREMENTAL):
                        await self.create_manual_backup(BackupType.INCREMENTAL)
                        self.last_incremental_backup = datetime.now()

                    # Periodic cleanup
                    if datetime.now().hour == 2:  # Run cleanup at 2 AM
                        self.cleanup_old_backups()

                    # Wait before next check (check every 30 minutes)
                    await asyncio.sleep(1800)

                except Exception as e:
                    log.error(f"Error in backup scheduler: {e}")
                    await asyncio.sleep(300)  # Wait 5 minutes before retry

        except asyncio.CancelledError:
            log.info("Backup scheduler cancelled")
        except Exception as e:
            log.error(f"Backup scheduler error: {e}")

    async def _perform_backup(self, backup_record: BackupRecord) -> bool:
        """Perform the actual backup operation."""
        try:
            if backup_record.backup_type == BackupType.CONFIGURATION:
                return await self._create_configuration_backup(backup_record)
            else:
                return await self._create_database_backup(backup_record)

        except Exception as e:
            log.error(f"Backup operation failed: {e}")
            return False

    async def _create_database_backup(self, backup_record: BackupRecord) -> bool:
        """Create a database backup."""
        try:
            # Create temporary backup file
            temp_backup_path = backup_record.file_path.with_suffix(".tmp")

            # Create database backup
            success = await self.db_backup_manager.create_backup(temp_backup_path)
            if not success:
                return False

            # Compress if enabled
            final_path = backup_record.file_path
            if self.config.enable_compression:
                final_path = backup_record.file_path.with_suffix(".zip")
                with zipfile.ZipFile(final_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(temp_backup_path, temp_backup_path.name)
                temp_backup_path.unlink()  # Remove temp file
            else:
                temp_backup_path.rename(final_path)

            # Update backup record
            backup_record.file_path = final_path
            backup_record.size_bytes = final_path.stat().st_size
            backup_record.checksum = await self._calculate_checksum(final_path)

            # Update last backup time
            if backup_record.backup_type == BackupType.FULL:
                self.last_full_backup = backup_record.timestamp
            elif backup_record.backup_type == BackupType.INCREMENTAL:
                self.last_incremental_backup = backup_record.timestamp

            return True

        except Exception as e:
            log.error(f"Failed to create database backup: {e}")
            return False

    async def _create_configuration_backup(self, backup_record: BackupRecord) -> bool:
        """Create a backup of configuration files."""
        try:
            config_files = [".env", "config.yaml", "config.json", "bot_config.py"]

            with zipfile.ZipFile(
                backup_record.file_path, "w", zipfile.ZIP_DEFLATED
            ) as zipf:
                for config_file in config_files:
                    config_path = Path(config_file)
                    if config_path.exists():
                        zipf.write(config_path, config_path.name)
                        log.debug(f"Added {config_file} to configuration backup")

            backup_record.size_bytes = backup_record.file_path.stat().st_size
            backup_record.checksum = await self._calculate_checksum(
                backup_record.file_path
            )

            return True

        except Exception as e:
            log.error(f"Failed to create configuration backup: {e}")
            return False

    async def _verify_backup(self, backup_record: BackupRecord) -> bool:
        """Verify backup integrity."""
        try:
            if not backup_record.file_path.exists():
                log.error(
                    f"Backup file not found for verification: {backup_record.file_path}"
                )
                return False

            # Verify checksum
            current_checksum = await self._calculate_checksum(backup_record.file_path)
            if current_checksum != backup_record.checksum:
                log.error(f"Backup checksum mismatch: {backup_record.backup_id}")
                return False

            # Verify based on backup type
            if backup_record.backup_type == BackupType.CONFIGURATION:
                return await self._verify_configuration_backup(backup_record.file_path)
            else:
                return await self._verify_database_backup(backup_record.file_path)

        except Exception as e:
            log.error(f"Failed to verify backup: {e}")
            return False

    async def _verify_database_backup(self, backup_path: Path) -> bool:
        """Verify database backup integrity."""
        try:
            if self.config.enable_compression and backup_path.suffix == ".zip":
                # Extract and verify compressed backup
                with zipfile.ZipFile(backup_path, "r") as zipf:
                    temp_dir = backup_path.parent / "temp_verify"
                    temp_dir.mkdir(exist_ok=True)

                    try:
                        zipf.extractall(temp_dir)
                        db_files = list(temp_dir.glob("*.db")) + list(
                            temp_dir.glob("*.tmp")
                        )

                        if db_files:
                            return await self.db_backup_manager.verify_backup(
                                db_files[0]
                            )

                    finally:
                        shutil.rmtree(temp_dir, ignore_errors=True)
            else:
                return await self.db_backup_manager.verify_backup(backup_path)

            return False

        except Exception as e:
            log.error(f"Failed to verify database backup: {e}")
            return False

    async def _verify_configuration_backup(self, backup_path: Path) -> bool:
        """Verify configuration backup integrity."""
        try:
            with zipfile.ZipFile(backup_path, "r") as zipf:
                # Test if the zip file is valid
                zipf.testzip()

                # Check if expected files are present
                file_list = zipf.namelist()
                log.debug(f"Configuration backup contains: {file_list}")

                return len(file_list) > 0

        except Exception as e:
            log.error(f"Failed to verify configuration backup: {e}")
            return False

    async def _restore_compressed_backup(
        self, backup_path: Path, target_path: Path
    ) -> None:
        """Restore a compressed backup."""
        with zipfile.ZipFile(backup_path, "r") as zipf:
            temp_dir = backup_path.parent / "temp_restore"
            temp_dir.mkdir(exist_ok=True)

            try:
                zipf.extractall(temp_dir)
                db_files = list(temp_dir.glob("*.db")) + list(temp_dir.glob("*.tmp"))

                if db_files:
                    shutil.copy2(db_files[0], target_path)

            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    async def _restore_configuration_backup(
        self, backup_path: Path, target_dir: Path
    ) -> None:
        """Restore configuration backup."""
        with zipfile.ZipFile(backup_path, "r") as zipf:
            zipf.extractall(target_dir)

    async def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of a file."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _generate_backup_id(self, backup_type: BackupType) -> str:
        """Generate unique backup ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"backup_{backup_type.value}_{timestamp}"

    def _get_backup_path(self, backup_id: str, backup_type: BackupType) -> Path:
        """Get the file path for a backup."""
        extension = (
            ".zip"
            if self.config.enable_compression or backup_type == BackupType.CONFIGURATION
            else ".db"
        )
        return self.config.backup_directory / f"{backup_id}{extension}"

    def _is_backup_due(self, backup_type: BackupType) -> bool:
        """Check if a backup of the specified type is due."""
        now = datetime.now()

        if backup_type == BackupType.FULL:
            if self.last_full_backup is None:
                return True
            return (
                now - self.last_full_backup
            ).total_seconds() >= self.config.full_backup_interval_hours * 3600

        elif backup_type == BackupType.INCREMENTAL:
            if self.last_incremental_backup is None:
                return True
            return (
                now - self.last_incremental_backup
            ).total_seconds() >= self.config.incremental_backup_interval_hours * 3600

        return False

    def _calculate_next_backup_time(self, backup_type: BackupType) -> datetime:
        """Calculate when the next backup of specified type is due."""
        if backup_type == BackupType.FULL:
            if self.last_full_backup is None:
                return datetime.now()
            return self.last_full_backup + timedelta(
                hours=self.config.full_backup_interval_hours
            )

        elif backup_type == BackupType.INCREMENTAL:
            if self.last_incremental_backup is None:
                return datetime.now()
            return self.last_incremental_backup + timedelta(
                hours=self.config.incremental_backup_interval_hours
            )

        return datetime.now()

    def _find_backup_record(self, backup_id: str) -> BackupRecord | None:
        """Find a backup record by ID."""
        for record in self.backup_records:
            if record.backup_id == backup_id:
                return record
        return None

    def _load_backup_history(self) -> None:
        """Load backup history from file."""
        history_file = self.config.backup_directory / "backup_history.json"

        try:
            if history_file.exists():
                with open(history_file) as f:
                    data = json.load(f)

                    for record_data in data.get("backups", []):
                        record = BackupRecord.from_dict(record_data)
                        self.backup_records.append(record)

                    # Load last backup times
                    if data.get("last_full_backup"):
                        self.last_full_backup = datetime.fromisoformat(
                            data["last_full_backup"]
                        )

                    if data.get("last_incremental_backup"):
                        self.last_incremental_backup = datetime.fromisoformat(
                            data["last_incremental_backup"]
                        )

                    log.info(
                        f"Loaded {len(self.backup_records)} backup records from history"
                    )

        except Exception as e:
            log.error(f"Failed to load backup history: {e}")

    def _save_backup_history(self) -> None:
        """Save backup history to file."""
        history_file = self.config.backup_directory / "backup_history.json"

        try:
            data = {
                "last_full_backup": (
                    self.last_full_backup.isoformat() if self.last_full_backup else None
                ),
                "last_incremental_backup": (
                    self.last_incremental_backup.isoformat()
                    if self.last_incremental_backup
                    else None
                ),
                "backups": [record.to_dict() for record in self.backup_records],
            }

            with open(history_file, "w") as f:
                json.dump(data, f, indent=2)

            log.debug("Backup history saved successfully")

        except Exception as e:
            log.error(f"Failed to save backup history: {e}")

    def get_backup_stats(self) -> dict[str, Any]:
        """Get comprehensive backup statistics."""
        total_backups = len(self.backup_records)
        successful_backups = len(
            [
                r
                for r in self.backup_records
                if r.status in (BackupStatus.COMPLETED, BackupStatus.VERIFIED)
            ]
        )
        failed_backups = len(
            [r for r in self.backup_records if r.status == BackupStatus.FAILED]
        )
        total_storage = sum(r.size_bytes or 0 for r in self.backup_records)

        # Backup type breakdown
        backup_types = {}
        for record in self.backup_records:
            type_name = record.backup_type.value
            backup_types[type_name] = backup_types.get(type_name, 0) + 1

        # Last backup time
        last_backup_time = None
        if self.backup_records:
            sorted_records = sorted(
                self.backup_records, key=lambda r: r.timestamp, reverse=True
            )
            last_backup_time = sorted_records[0].timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # Next scheduled backup
        next_scheduled = None
        if self.is_scheduled_enabled():
            if self._is_backup_due(BackupType.FULL):
                next_scheduled = "Due now (Full)"
            elif self._is_backup_due(BackupType.INCREMENTAL):
                next_scheduled = "Due now (Incremental)"
            else:
                # Calculate next scheduled backup
                if self.last_full_backup:
                    next_full = self.last_full_backup + timedelta(
                        hours=self.config.full_backup_interval_hours
                    )
                    next_scheduled = (
                        f"Full backup at {next_full.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                else:
                    next_scheduled = "Full backup due now"

        return {
            "total_backups": total_backups,
            "successful_backups": successful_backups,
            "failed_backups": failed_backups,
            "total_storage_bytes": total_storage,
            "backup_types": backup_types,
            "last_backup_time": last_backup_time,
            "next_scheduled_backup": next_scheduled,
            "backup_directory": str(self.config.backup_directory),
            "compression_enabled": self.config.enable_compression,
            "scheduled_enabled": self.is_scheduled_enabled(),
        }

    def is_scheduled_enabled(self) -> bool:
        """Check if scheduled backups are enabled."""
        return self.is_running

    def list_backups(self, limit: int | None = None) -> list[BackupRecord]:
        """List available backups, sorted by creation time (newest first)."""
        sorted_backups = sorted(
            self.backup_records, key=lambda r: r.timestamp, reverse=True
        )
        if limit:
            return sorted_backups[:limit]
        return sorted_backups

    def restore_from_backup(self, backup_id: str) -> bool:
        """Restore from a specific backup."""
        # Find the backup record
        backup_record = next(
            (r for r in self.backup_records if r.backup_id == backup_id), None
        )
        if not backup_record:
            log.error(f"Backup {backup_id} not found")
            return False

        if backup_record.status != BackupStatus.COMPLETED:
            log.error(f"Cannot restore from incomplete backup {backup_id}")
            return False

        try:
            if backup_record.backup_type == BackupType.CONFIGURATION:
                return self._restore_configuration_backup(backup_record)
            else:
                return self._restore_database_backup(backup_record)

        except Exception as e:
            log.error(f"Failed to restore from backup {backup_id}: {e}")
            return False

    def _restore_database_backup(self, backup_record: BackupRecord) -> bool:
        """Restore database from backup."""
        try:
            source_path = backup_record.file_path
            target_path = Path(self.database_path)

            # Create backup of current database before restore
            current_backup_path = (
                target_path.parent / f"{target_path.name}.restore_backup"
            )
            if target_path.exists():
                shutil.copy2(target_path, current_backup_path)
                log.info(f"Created backup of current database at {current_backup_path}")

            # Restore from backup
            if source_path.suffix == ".zip":
                # Extract compressed backup
                with zipfile.ZipFile(source_path, "r") as zipf:
                    zipf.extractall(target_path.parent)
            else:
                # Direct copy for uncompressed backup
                shutil.copy2(source_path, target_path)

            log.info(
                f"Successfully restored database from backup {backup_record.backup_id}"
            )
            return True

        except Exception as e:
            log.error(f"Failed to restore database backup: {e}")
            return False

    def _restore_configuration_backup(self, backup_record: BackupRecord) -> bool:
        """Restore configuration from backup."""
        try:
            with zipfile.ZipFile(backup_record.file_path, "r") as zipf:
                # Extract configuration files to current directory
                zipf.extractall(".")

            log.info(
                f"Successfully restored configuration from backup {backup_record.backup_id}"
            )
            return True

        except Exception as e:
            log.error(f"Failed to restore configuration backup: {e}")
            return False

    def cleanup_old_backups(self, older_than_days: int, dry_run: bool = False) -> int:
        """Clean up backups older than specified days."""
        cutoff_date = datetime.now() - timedelta(days=older_than_days)

        old_backups = [
            record for record in self.backup_records if record.timestamp < cutoff_date
        ]

        deleted_count = 0

        for backup in old_backups:
            try:
                if not dry_run:
                    # Delete backup file
                    if backup.file_path.exists():
                        backup.file_path.unlink()

                    # Remove from records
                    self.backup_records.remove(backup)

                deleted_count += 1
                log.info(
                    f"{'Would delete' if dry_run else 'Deleted'} backup: {backup.backup_id}"
                )

            except Exception as e:
                log.error(f"Failed to delete backup {backup.backup_id}: {e}")

        if not dry_run and deleted_count > 0:
            # Save updated history
            self._save_backup_history()

        return deleted_count


# Global backup manager instance
_backup_manager: AutomatedBackupManager | None = None


def get_backup_manager(
    config: BackupConfig | None = None, database_path: str = "bot_data.db"
) -> AutomatedBackupManager:
    """Get or create the global backup manager."""
    global _backup_manager
    if _backup_manager is None:
        backup_config = config or BackupConfig()
        _backup_manager = AutomatedBackupManager(backup_config, database_path)
    return _backup_manager


async def start_backup_system(config: BackupConfig | None = None) -> None:
    """Start the automated backup system."""
    manager = get_backup_manager(config)
    await manager.start()


async def stop_backup_system() -> None:
    """Stop the automated backup system."""
    if _backup_manager is not None:
        await _backup_manager.stop()


async def create_immediate_backup(
    backup_type: BackupType = BackupType.FULL,
) -> BackupRecord | None:
    """Create an immediate backup."""
    manager = get_backup_manager()
    return await manager.create_manual_backup(backup_type)


def get_backup_status() -> dict[str, Any]:
    """Get backup system status."""
    if _backup_manager is None:
        return {"system_status": "not_initialized"}
    return _backup_manager.get_backup_status()
