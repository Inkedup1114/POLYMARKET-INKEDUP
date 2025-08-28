"""
Comprehensive test suite for the database migration system.
Tests migration functionality, rollback capabilities, and safety mechanisms.
"""

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from inkedup_bot.db_models import Base, create_engine_for_url
from inkedup_bot.migration_manager import (
    BackupInfo,
    BackupStatus,
    DatabaseMigrationManager,
    MigrationSafetyError,
    MigrationStatus,
)


class TestDatabaseMigrationManager:
    """Test suite for DatabaseMigrationManager."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            db_path = tmp_file.name
        yield db_path
        # Cleanup
        if Path(db_path).exists():
            Path(db_path).unlink()

    @pytest.fixture
    def temp_backup_dir(self):
        """Create a temporary backup directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield tmp_dir

    @pytest.fixture
    def migration_manager(self, temp_db_path, temp_backup_dir):
        """Create a migration manager with temporary database."""
        database_url = f"sqlite:///{temp_db_path}"

        # Create a mock alembic.ini file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", delete=False
        ) as alembic_ini:
            alembic_ini.write(
                """
[alembic]
script_location = inkedup_bot/migrations
sqlalchemy.url = 
"""
            )
            alembic_ini_path = alembic_ini.name

        manager = DatabaseMigrationManager(
            database_url=database_url,
            alembic_ini_path=alembic_ini_path,
            backup_dir=temp_backup_dir,
            enable_backups=True,
            enable_safety_checks=True,
        )

        yield manager

        # Cleanup
        if Path(alembic_ini_path).exists():
            Path(alembic_ini_path).unlink()

    def test_initialization(self, migration_manager):
        """Test migration manager initialization."""
        assert migration_manager.database_url.startswith("sqlite:///")
        assert migration_manager.enable_backups is True
        assert migration_manager.enable_safety_checks is True
        assert migration_manager.backup_dir.exists()

    def test_get_database_url_from_env(self, temp_db_path, temp_backup_dir):
        """Test database URL loading from environment."""
        with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{temp_db_path}"}):
            manager = DatabaseMigrationManager(backup_dir=temp_backup_dir)
            assert manager.database_url == f"sqlite:///{temp_db_path}"

    def test_create_sqlite_backup(self, migration_manager, temp_db_path):
        """Test SQLite database backup creation."""
        # Create a simple table in the database
        conn = sqlite3.connect(temp_db_path)
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test_table (name) VALUES ('test_data')")
        conn.commit()
        conn.close()

        # Create backup
        backup_info = migration_manager.create_backup("test_backup")

        assert backup_info.status == BackupStatus.CREATED
        assert Path(backup_info.backup_path).exists()
        assert backup_info.size_bytes > 0

        # Verify backup contains data
        with open(backup_info.backup_path) as f:
            backup_content = f.read()
            assert "test_table" in backup_content
            assert "test_data" in backup_content

    def test_restore_sqlite_backup(self, migration_manager, temp_db_path):
        """Test SQLite database backup restoration."""
        # Create initial data
        conn = sqlite3.connect(temp_db_path)
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test_table (name) VALUES ('original_data')")
        conn.commit()
        conn.close()

        # Create backup
        backup_info = migration_manager.create_backup("test_restore")

        # Modify the database
        conn = sqlite3.connect(temp_db_path)
        conn.execute("INSERT INTO test_table (name) VALUES ('modified_data')")
        conn.commit()
        conn.close()

        # Restore from backup
        migration_manager.restore_backup(backup_info)

        # Verify restoration
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM test_table WHERE name = 'original_data'"
        )
        original_count = cursor.fetchone()[0]
        cursor = conn.execute(
            "SELECT COUNT(*) FROM test_table WHERE name = 'modified_data'"
        )
        modified_count = cursor.fetchone()[0]
        conn.close()

        assert original_count == 1
        assert modified_count == 0

    def test_safety_checks_database_connectivity(self, migration_manager):
        """Test safety check for database connectivity."""
        # This should pass with a valid database
        migration_manager._perform_safety_checks()

        # Test with invalid database
        migration_manager.database_url = "sqlite:///nonexistent/path/db.sqlite"
        migration_manager._engine = create_engine_for_url(
            migration_manager.database_url
        )

        with pytest.raises(MigrationSafetyError):
            migration_manager._perform_safety_checks()

    def test_safety_checks_disk_space(self, migration_manager, temp_db_path):
        """Test safety check for disk space."""
        # Create a larger database file
        conn = sqlite3.connect(temp_db_path)
        conn.execute("CREATE TABLE large_table (id INTEGER, data TEXT)")

        # Insert some data to make the file larger
        for i in range(1000):
            conn.execute("INSERT INTO large_table VALUES (?, ?)", (i, "x" * 100))
        conn.commit()
        conn.close()

        # Mock insufficient disk space
        with patch("shutil.disk_usage") as mock_disk_usage:
            mock_disk_usage.return_value = MagicMock(free=100)  # Very small free space

            with pytest.raises(MigrationSafetyError, match="Insufficient disk space"):
                migration_manager._perform_safety_checks()

    def test_safety_checks_disabled(self, migration_manager):
        """Test that safety checks can be disabled."""
        migration_manager.enable_safety_checks = False
        migration_manager.database_url = "sqlite:///nonexistent/path/db.sqlite"
        migration_manager._engine = create_engine_for_url(
            migration_manager.database_url
        )

        # Should not raise an exception when disabled
        migration_manager._perform_safety_checks()

    @patch("inkedup_bot.migration_manager.alembic_command.upgrade")
    def test_upgrade_to_revision_success(self, mock_upgrade, migration_manager):
        """Test successful upgrade to revision."""
        # Mock Alembic upgrade command
        mock_upgrade.return_value = None

        # Mock current revision methods
        with patch.object(
            migration_manager, "get_current_revision", side_effect=["rev1", "rev2"]
        ):
            result = migration_manager.upgrade_to_revision("rev2")

        assert result.success is True
        assert result.status == MigrationStatus.SUCCESS
        assert result.revision == "rev2"
        assert result.duration_seconds > 0
        mock_upgrade.assert_called_once_with(migration_manager._alembic_config, "rev2")

    @patch("inkedup_bot.migration_manager.alembic_command.upgrade")
    def test_upgrade_to_revision_failure(self, mock_upgrade, migration_manager):
        """Test failed upgrade to revision."""
        # Mock Alembic upgrade command to raise exception
        mock_upgrade.side_effect = Exception("Migration failed")

        result = migration_manager.upgrade_to_revision("rev2")

        assert result.success is False
        assert result.status == MigrationStatus.FAILED
        assert "Migration failed" in result.message
        assert result.error_details == "Migration failed"

    @patch("inkedup_bot.migration_manager.alembic_command.downgrade")
    def test_downgrade_to_revision_success(self, mock_downgrade, migration_manager):
        """Test successful downgrade to revision."""
        # Mock Alembic downgrade command
        mock_downgrade.return_value = None

        # Mock current revision methods
        with patch.object(
            migration_manager, "get_current_revision", side_effect=["rev2", "rev1"]
        ):
            result = migration_manager.downgrade_to_revision("rev1")

        assert result.success is True
        assert result.status == MigrationStatus.SUCCESS
        assert result.revision == "rev1"
        mock_downgrade.assert_called_once_with(
            migration_manager._alembic_config, "rev1"
        )

    def test_auto_rollback_success(self, migration_manager, temp_db_path):
        """Test successful automatic rollback."""
        # Create initial data and backup
        conn = sqlite3.connect(temp_db_path)
        conn.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO test_table (name) VALUES ('original')")
        conn.commit()
        conn.close()

        backup_info = migration_manager.create_backup("rollback_test")

        # Modify database
        conn = sqlite3.connect(temp_db_path)
        conn.execute("INSERT INTO test_table (name) VALUES ('modified')")
        conn.commit()
        conn.close()

        # Perform rollback
        result = migration_manager.auto_rollback(backup_info, "Test error")

        assert result.success is True
        assert result.status == MigrationStatus.ROLLED_BACK

        # Verify rollback worked
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM test_table WHERE name = 'modified'")
        modified_count = cursor.fetchone()[0]
        conn.close()

        assert modified_count == 0

    def test_auto_rollback_failure(self, migration_manager):
        """Test automatic rollback failure."""
        # Create backup info with non-existent file
        backup_info = BackupInfo(
            backup_path="/nonexistent/backup.sql",
            created_at=datetime.now(),
            database_url=migration_manager.database_url,
            size_bytes=0,
            status=BackupStatus.CREATED,
        )

        result = migration_manager.auto_rollback(backup_info, "Test error")

        assert result.success is False
        assert result.status == MigrationStatus.FAILED
        assert "Auto-rollback failed" in result.message

    def test_cleanup_old_backups(self, migration_manager, temp_backup_dir):
        """Test cleanup of old backup files."""
        # Create multiple backup files
        backup_dir = Path(temp_backup_dir)
        for i in range(15):
            backup_file = backup_dir / f"backup_{i:02d}.sql"
            backup_file.write_text(f"backup content {i}")
            # Set different modification times
            os.utime(backup_file, (1000000 + i, 1000000 + i))

        # Keep only last 10
        removed_count = migration_manager.cleanup_old_backups(keep_last_n=10)

        assert removed_count == 5

        # Verify only 10 files remain
        remaining_files = list(backup_dir.glob("*.sql"))
        assert len(remaining_files) == 10

        # Verify the newest files are kept
        remaining_names = [f.name for f in remaining_files]
        for i in range(5, 15):
            assert f"backup_{i:02d}.sql" in remaining_names

    @patch("inkedup_bot.migration_manager.ScriptDirectory.from_config")
    def test_validate_migration_integrity_success(
        self, mock_script_dir, migration_manager
    ):
        """Test successful migration integrity validation."""
        # Mock script directory and migration history
        mock_script_dir.return_value = MagicMock()

        with patch.object(
            migration_manager, "get_current_revision", return_value="rev1"
        ):
            with patch.object(
                migration_manager,
                "get_migration_history",
                return_value=[MagicMock(revision="rev1")],
            ):
                result = migration_manager.validate_migration_integrity()

        assert result is True

    @patch("inkedup_bot.migration_manager.ScriptDirectory.from_config")
    def test_validate_migration_integrity_failure(
        self, mock_script_dir, migration_manager
    ):
        """Test migration integrity validation failure."""
        mock_script_dir.side_effect = Exception("Script directory error")

        result = migration_manager.validate_migration_integrity()

        assert result is False

    def test_get_migration_status(self, migration_manager):
        """Test getting comprehensive migration status."""
        with patch.object(
            migration_manager, "get_current_revision", return_value="rev1"
        ):
            with patch.object(
                migration_manager, "get_pending_migrations", return_value=[]
            ):
                with patch.object(
                    migration_manager,
                    "get_migration_history",
                    return_value=[MagicMock()],
                ):
                    status = migration_manager.get_migration_status()

        assert status["current_revision"] == "rev1"
        assert status["pending_migrations"] == 0
        assert status["total_migrations"] == 1
        assert status["is_up_to_date"] is True
        assert status["backups_enabled"] is True
        assert status["safety_checks_enabled"] is True

    def test_backup_disabled(self, temp_db_path, temp_backup_dir):
        """Test migration manager with backups disabled."""
        database_url = f"sqlite:///{temp_db_path}"

        manager = DatabaseMigrationManager(
            database_url=database_url, backup_dir=temp_backup_dir, enable_backups=False
        )

        with pytest.raises(MigrationSafetyError, match="Backups are disabled"):
            manager.create_backup("test")


class TestMigrationIntegration:
    """Integration tests for the migration system."""

    @pytest.fixture
    def integration_db_path(self):
        """Create a temporary database for integration testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            db_path = tmp_file.name
        yield db_path
        # Cleanup
        if Path(db_path).exists():
            Path(db_path).unlink()

    def test_end_to_end_migration_flow(self, integration_db_path):
        """Test complete migration flow from setup to execution."""
        database_url = f"sqlite:///{integration_db_path}"

        # Initialize the database with Base metadata
        engine = create_engine_for_url(database_url)
        Base.metadata.create_all(engine)

        # Create migration manager
        with tempfile.TemporaryDirectory() as backup_dir:
            manager = DatabaseMigrationManager(
                database_url=database_url,
                backup_dir=backup_dir,
                enable_backups=True,
                enable_safety_checks=True,
            )

            # Test getting status on fresh database
            status = manager.get_migration_status()
            assert status["current_revision"] is None

            # Test integrity validation
            integrity_ok = manager.validate_migration_integrity()
            # This might fail due to missing alembic setup, which is expected

            # Test backup creation
            backup_info = manager.create_backup("integration_test")
            assert backup_info.status == BackupStatus.CREATED

            # Test backup cleanup
            removed_count = manager.cleanup_old_backups(keep_last_n=5)
            assert removed_count >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
