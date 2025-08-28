"""
Database migration management system with safety features and rollback capabilities.
Provides a high-level interface for managing database schema evolution safely in production.
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from .config import BotConfig
from .db_models import create_engine_for_url, get_database_url

log = logging.getLogger("migration_manager")


class MigrationStatus(Enum):
    """Migration execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class BackupStatus(Enum):
    """Database backup status."""

    CREATED = "created"
    FAILED = "failed"
    RESTORED = "restored"
    CLEANUP = "cleanup"


@dataclass
class MigrationInfo:
    """Information about a migration."""

    revision: str
    description: str
    is_applied: bool
    applied_at: datetime | None = None
    branch_labels: list[str] | None = None
    depends_on: str | None = None


@dataclass
class BackupInfo:
    """Information about a database backup."""

    backup_path: str
    created_at: datetime
    database_url: str
    size_bytes: int
    status: BackupStatus


@dataclass
class MigrationResult:
    """Result of a migration operation."""

    success: bool
    status: MigrationStatus
    revision: str | None
    message: str
    duration_seconds: float
    backup_info: BackupInfo | None = None
    error_details: str | None = None


class MigrationSafetyError(Exception):
    """Raised when migration safety checks fail."""

    pass


class DatabaseMigrationManager:
    """
    Comprehensive database migration manager with safety features.

    Features:
    - Automatic backups before migrations
    - Rollback capabilities
    - Production safety checks
    - Migration validation
    - Progress tracking
    """

    def __init__(
        self,
        database_url: str | None = None,
        alembic_ini_path: str | None = None,
        backup_dir: str | None = None,
        enable_backups: bool = True,
        enable_safety_checks: bool = True,
    ):
        self.database_url = database_url or self._get_database_url()
        self.alembic_ini_path = alembic_ini_path or "alembic.ini"
        self.backup_dir = Path(backup_dir or "backups/migrations")
        self.enable_backups = enable_backups
        self.enable_safety_checks = enable_safety_checks

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Initialize Alembic config
        self._alembic_config = self._create_alembic_config()
        self._engine = create_engine_for_url(self.database_url)

        # Migration state tracking
        self._current_operation: str | None = None
        self._operation_start_time: float | None = None

    def _get_database_url(self) -> str:
        """Get database URL from configuration."""
        # Try environment variable first
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            return get_database_url(db_url)

        # Load from bot config
        try:
            config = BotConfig()
            return get_database_url(config.database_url)
        except Exception as e:
            log.warning(f"Could not load config: {e}, using default")
            return get_database_url("sqlite:///bot_data.db")

    def _create_alembic_config(self) -> AlembicConfig:
        """Create Alembic configuration."""
        config = AlembicConfig(self.alembic_ini_path)

        # Override database URL in config
        config.set_main_option("sqlalchemy.url", self.database_url)

        return config

    def get_current_revision(self) -> str | None:
        """Get the current database revision."""
        try:
            with self._engine.connect() as conn:
                # Check if alembic_version table exists
                inspector = inspect(self._engine)
                if "alembic_version" not in inspector.get_table_names():
                    return None

                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                row = result.fetchone()
                return row[0] if row else None
        except Exception as e:
            log.error(f"Error getting current revision: {e}")
            return None

    def get_migration_history(self) -> list[MigrationInfo]:
        """Get complete migration history."""
        try:
            script_dir = ScriptDirectory.from_config(self._alembic_config)
            current_rev = self.get_current_revision()

            migrations = []
            for revision in script_dir.walk_revisions():
                is_applied = (
                    current_rev is not None
                    and script_dir.get_revision(current_rev) is not None
                    and revision.revision
                    in [
                        r.revision
                        for r in script_dir.walk_revisions("base", current_rev)
                    ]
                )

                migration = MigrationInfo(
                    revision=revision.revision,
                    description=revision.doc or "No description",
                    is_applied=is_applied,
                    branch_labels=(
                        list(revision.branch_labels) if revision.branch_labels else None
                    ),
                    depends_on=revision.down_revision,
                )
                migrations.append(migration)

            return sorted(migrations, key=lambda m: m.revision)
        except Exception as e:
            log.error(f"Error getting migration history: {e}")
            return []

    def get_pending_migrations(self) -> list[MigrationInfo]:
        """Get list of pending migrations."""
        history = self.get_migration_history()
        return [m for m in history if not m.is_applied]

    def create_backup(self, backup_name: str | None = None) -> BackupInfo:
        """Create a database backup before migration."""
        if not self.enable_backups:
            log.info("Backups disabled, skipping backup creation")
            raise MigrationSafetyError("Backups are disabled")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = backup_name or f"pre_migration_{timestamp}"
        backup_path = self.backup_dir / f"{backup_name}.sql"

        log.info(f"Creating backup: {backup_path}")

        try:
            if self.database_url.startswith("sqlite:"):
                self._create_sqlite_backup(backup_path)
            elif self.database_url.startswith(("postgresql:", "postgres:")):
                self._create_postgresql_backup(backup_path)
            else:
                raise MigrationSafetyError(
                    f"Backup not supported for database type: {self.database_url}"
                )

            # Get backup file size
            size_bytes = backup_path.stat().st_size

            backup_info = BackupInfo(
                backup_path=str(backup_path),
                created_at=datetime.now(),
                database_url=self.database_url,
                size_bytes=size_bytes,
                status=BackupStatus.CREATED,
            )

            log.info(f"Backup created successfully: {backup_path} ({size_bytes} bytes)")
            return backup_info

        except Exception as e:
            log.error(f"Backup creation failed: {e}")
            backup_info = BackupInfo(
                backup_path=str(backup_path),
                created_at=datetime.now(),
                database_url=self.database_url,
                size_bytes=0,
                status=BackupStatus.FAILED,
            )
            raise MigrationSafetyError(f"Backup creation failed: {e}") from e

    def _create_sqlite_backup(self, backup_path: Path) -> None:
        """Create SQLite database backup using Python sqlite3 module."""
        if self.database_url == "sqlite:///:memory:":
            raise MigrationSafetyError("Cannot backup in-memory SQLite database")

        # Extract file path from URL
        db_file = self.database_url.replace("sqlite:///", "")
        source_path = Path(db_file)

        if not source_path.exists():
            raise MigrationSafetyError(
                f"Source database file does not exist: {source_path}"
            )

        # Use Python sqlite3 module to create backup
        import sqlite3

        try:
            # Open source database
            source_conn = sqlite3.connect(str(source_path))

            # Create backup file and write SQL dump
            with open(backup_path, "w") as backup_file:
                for line in source_conn.iterdump():
                    backup_file.write(f"{line}\n")

            source_conn.close()

        except sqlite3.Error as e:
            raise MigrationSafetyError(f"SQLite backup failed: {e}")

    def _create_postgresql_backup(self, backup_path: Path) -> None:
        """Create PostgreSQL database backup."""
        # Parse PostgreSQL URL
        import urllib.parse as urlparse

        parsed = urlparse.urlparse(self.database_url)

        # Set environment variables for pg_dump
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password

        cmd = [
            "pg_dump",
            "-h",
            parsed.hostname or "localhost",
            "-p",
            str(parsed.port or 5432),
            "-U",
            parsed.username or "postgres",
            "-d",
            parsed.path.lstrip("/") if parsed.path else "postgres",
            "--no-password",
            "--verbose",
            "--clean",
            "--if-exists",
            "--create",
        ]

        with open(backup_path, "w") as backup_file:
            result = subprocess.run(
                cmd, stdout=backup_file, stderr=subprocess.PIPE, text=True, env=env
            )
            if result.returncode != 0:
                raise MigrationSafetyError(f"PostgreSQL dump failed: {result.stderr}")

    def restore_backup(self, backup_info: BackupInfo) -> None:
        """Restore database from backup."""
        backup_path = Path(backup_info.backup_path)

        if not backup_path.exists():
            raise MigrationSafetyError(f"Backup file does not exist: {backup_path}")

        log.info(f"Restoring backup: {backup_path}")

        try:
            if self.database_url.startswith("sqlite:"):
                self._restore_sqlite_backup(backup_path)
            elif self.database_url.startswith(("postgresql:", "postgres:")):
                self._restore_postgresql_backup(backup_path)
            else:
                raise MigrationSafetyError(
                    f"Restore not supported for database type: {self.database_url}"
                )

            log.info(f"Backup restored successfully from: {backup_path}")

        except Exception as e:
            log.error(f"Backup restore failed: {e}")
            raise MigrationSafetyError(f"Backup restore failed: {e}") from e

    def _restore_sqlite_backup(self, backup_path: Path) -> None:
        """Restore SQLite database from backup using Python sqlite3 module."""
        if self.database_url == "sqlite:///:memory:":
            raise MigrationSafetyError("Cannot restore to in-memory SQLite database")

        # Extract file path from URL
        db_file = self.database_url.replace("sqlite:///", "")
        target_path = Path(db_file)

        # Remove existing database
        if target_path.exists():
            target_path.unlink()

        # Use Python sqlite3 module to restore from backup
        import sqlite3

        try:
            # Create new database connection
            target_conn = sqlite3.connect(str(target_path))

            # Read and execute backup SQL
            with open(backup_path) as backup_file:
                backup_sql = backup_file.read()
                target_conn.executescript(backup_sql)

            target_conn.close()

        except sqlite3.Error as e:
            raise MigrationSafetyError(f"SQLite restore failed: {e}")

    def _restore_postgresql_backup(self, backup_path: Path) -> None:
        """Restore PostgreSQL database from backup."""
        # Parse PostgreSQL URL
        import urllib.parse as urlparse

        parsed = urlparse.urlparse(self.database_url)

        # Set environment variables for psql
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password

        cmd = [
            "psql",
            "-h",
            parsed.hostname or "localhost",
            "-p",
            str(parsed.port or 5432),
            "-U",
            parsed.username or "postgres",
            "-d",
            "postgres",  # Connect to postgres database first
            "-f",
            str(backup_path),
            "--quiet",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            raise MigrationSafetyError(f"PostgreSQL restore failed: {result.stderr}")

    def _perform_safety_checks(self) -> None:
        """Perform pre-migration safety checks."""
        if not self.enable_safety_checks:
            log.info("Safety checks disabled")
            return

        log.info("Performing pre-migration safety checks")

        # Check database connectivity
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise MigrationSafetyError(f"Database connectivity check failed: {e}")

        # Check for active connections (PostgreSQL only)
        if self.database_url.startswith(("postgresql:", "postgres:")):
            try:
                with self._engine.connect() as conn:
                    result = conn.execute(
                        text(
                            "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active' AND pid != pg_backend_pid()"
                        )
                    )
                    active_connections = result.scalar()
                    if active_connections > 5:  # Configurable threshold
                        log.warning(
                            f"High number of active connections detected: {active_connections}"
                        )
            except Exception as e:
                log.warning(f"Could not check active connections: {e}")

        # Check available disk space (basic check)
        import shutil

        if self.database_url.startswith("sqlite:") and not self.database_url.endswith(
            ":memory:"
        ):
            db_path = Path(self.database_url.replace("sqlite:///", ""))
            if db_path.exists():
                db_size = db_path.stat().st_size
                free_space = shutil.disk_usage(db_path.parent).free
                if free_space < db_size * 2:  # Require 2x database size free space
                    raise MigrationSafetyError(
                        f"Insufficient disk space. Need {db_size * 2}, have {free_space}"
                    )

        log.info("All safety checks passed")

    def upgrade_to_revision(self, revision: str = "head") -> MigrationResult:
        """Upgrade database to a specific revision."""
        start_time = time.time()
        backup_info = None

        try:
            log.info(f"Starting migration to revision: {revision}")
            self._current_operation = f"upgrade to {revision}"
            self._operation_start_time = start_time

            # Pre-migration checks
            self._perform_safety_checks()

            # Create backup if enabled
            if self.enable_backups:
                backup_info = self.create_backup(
                    f"pre_upgrade_{revision}_{int(start_time)}"
                )

            # Get current revision for logging
            current_rev = self.get_current_revision()
            log.info(f"Current revision: {current_rev}, target: {revision}")

            # Perform the migration
            alembic_command.upgrade(self._alembic_config, revision)

            duration = time.time() - start_time

            # Verify migration success
            new_rev = self.get_current_revision()
            if revision != "head" and new_rev != revision:
                raise MigrationSafetyError(
                    f"Migration verification failed. Expected {revision}, got {new_rev}"
                )

            result = MigrationResult(
                success=True,
                status=MigrationStatus.SUCCESS,
                revision=new_rev,
                message=f"Successfully upgraded from {current_rev} to {new_rev}",
                duration_seconds=duration,
                backup_info=backup_info,
            )

            log.info(f"Migration completed successfully in {duration:.2f}s")
            return result

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Migration failed: {str(e)}"
            log.error(error_msg)

            result = MigrationResult(
                success=False,
                status=MigrationStatus.FAILED,
                revision=None,
                message=error_msg,
                duration_seconds=duration,
                backup_info=backup_info,
                error_details=str(e),
            )

            return result
        finally:
            self._current_operation = None
            self._operation_start_time = None

    def downgrade_to_revision(self, revision: str) -> MigrationResult:
        """Downgrade database to a specific revision."""
        start_time = time.time()
        backup_info = None

        try:
            log.info(f"Starting downgrade to revision: {revision}")
            self._current_operation = f"downgrade to {revision}"
            self._operation_start_time = start_time

            # Pre-migration checks
            self._perform_safety_checks()

            # Create backup if enabled
            if self.enable_backups:
                backup_info = self.create_backup(
                    f"pre_downgrade_{revision}_{int(start_time)}"
                )

            # Get current revision for logging
            current_rev = self.get_current_revision()
            log.info(f"Current revision: {current_rev}, target: {revision}")

            # Perform the downgrade
            alembic_command.downgrade(self._alembic_config, revision)

            duration = time.time() - start_time

            # Verify downgrade success
            new_rev = self.get_current_revision()
            if new_rev != revision:
                raise MigrationSafetyError(
                    f"Downgrade verification failed. Expected {revision}, got {new_rev}"
                )

            result = MigrationResult(
                success=True,
                status=MigrationStatus.SUCCESS,
                revision=new_rev,
                message=f"Successfully downgraded from {current_rev} to {new_rev}",
                duration_seconds=duration,
                backup_info=backup_info,
            )

            log.info(f"Downgrade completed successfully in {duration:.2f}s")
            return result

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Downgrade failed: {str(e)}"
            log.error(error_msg)

            result = MigrationResult(
                success=False,
                status=MigrationStatus.FAILED,
                revision=None,
                message=error_msg,
                duration_seconds=duration,
                backup_info=backup_info,
                error_details=str(e),
            )

            return result
        finally:
            self._current_operation = None
            self._operation_start_time = None

    def create_migration(self, message: str, autogenerate: bool = True) -> str:
        """Create a new migration."""
        log.info(f"Creating new migration: {message}")

        try:
            if autogenerate:
                # Use autogenerate to detect model changes
                alembic_command.revision(
                    self._alembic_config, message=message, autogenerate=True
                )
            else:
                # Create empty migration
                alembic_command.revision(self._alembic_config, message=message)

            # Get the newly created revision
            script_dir = ScriptDirectory.from_config(self._alembic_config)
            current_head = script_dir.get_current_head()

            log.info(f"Migration created successfully: {current_head}")
            return current_head

        except Exception as e:
            log.error(f"Failed to create migration: {e}")
            raise

    def get_migration_status(self) -> dict[str, Any]:
        """Get comprehensive migration status."""
        current_rev = self.get_current_revision()
        pending = self.get_pending_migrations()
        history = self.get_migration_history()

        return {
            "current_revision": current_rev,
            "pending_migrations": len(pending),
            "total_migrations": len(history),
            "is_up_to_date": len(pending) == 0,
            "database_url": (
                self.database_url.split("@")[-1]
                if "@" in self.database_url
                else self.database_url
            ),
            "current_operation": self._current_operation,
            "operation_duration": (
                time.time() - self._operation_start_time
                if self._operation_start_time
                else None
            ),
            "backups_enabled": self.enable_backups,
            "safety_checks_enabled": self.enable_safety_checks,
        }

    def auto_rollback(
        self, backup_info: BackupInfo, error_context: str
    ) -> MigrationResult:
        """Automatically rollback to a previous state using backup."""
        log.warning(f"Performing auto-rollback due to: {error_context}")
        start_time = time.time()

        try:
            self.restore_backup(backup_info)
            duration = time.time() - start_time

            result = MigrationResult(
                success=True,
                status=MigrationStatus.ROLLED_BACK,
                revision=None,
                message=f"Successfully rolled back using backup from {backup_info.created_at}",
                duration_seconds=duration,
                backup_info=backup_info,
            )

            log.info(f"Auto-rollback completed in {duration:.2f}s")
            return result

        except Exception as e:
            duration = time.time() - start_time
            error_msg = f"Auto-rollback failed: {str(e)}"
            log.error(error_msg)

            return MigrationResult(
                success=False,
                status=MigrationStatus.FAILED,
                revision=None,
                message=error_msg,
                duration_seconds=duration,
                backup_info=backup_info,
                error_details=str(e),
            )

    def cleanup_old_backups(self, keep_last_n: int = 10) -> int:
        """Clean up old backup files, keeping only the most recent N."""
        if not self.backup_dir.exists():
            return 0

        backup_files = list(self.backup_dir.glob("*.sql"))
        backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        files_to_remove = backup_files[keep_last_n:]
        removed_count = 0

        for backup_file in files_to_remove:
            try:
                backup_file.unlink()
                removed_count += 1
                log.info(f"Removed old backup: {backup_file}")
            except Exception as e:
                log.warning(f"Could not remove backup {backup_file}: {e}")

        return removed_count

    def validate_migration_integrity(self) -> bool:
        """Validate the integrity of the migration system."""
        try:
            # Check if Alembic is properly initialized
            script_dir = ScriptDirectory.from_config(self._alembic_config)

            # Check if migration table exists and is accessible
            current_rev = self.get_current_revision()

            # Verify we can read migration history
            history = self.get_migration_history()

            # Basic sanity checks
            if current_rev is not None and not any(
                m.revision == current_rev for m in history
            ):
                log.error(
                    f"Current revision {current_rev} not found in migration history"
                )
                return False

            log.info("Migration system integrity check passed")
            return True

        except Exception as e:
            log.error(f"Migration integrity check failed: {e}")
            return False
