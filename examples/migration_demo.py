"""
Migration system demonstration and usage examples.
Shows how to use the DatabaseMigrationManager for various scenarios.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inkedup_bot.db_models import Base, create_engine_for_url
from inkedup_bot.migration_manager import DatabaseMigrationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log = logging.getLogger("migration_demo")


def demo_migration_status():
    """Demonstrate how to check migration status."""
    log.info("=== Migration Status Demo ===")

    try:
        manager = DatabaseMigrationManager(
            database_url="sqlite:///demo_migration.db",
            backup_dir="demo_backups",
            enable_backups=True,
            enable_safety_checks=True,
        )

        # Get comprehensive status
        status = manager.get_migration_status()

        log.info("Migration Status:")
        log.info(f"  Current revision: {status['current_revision']}")
        log.info(f"  Pending migrations: {status['pending_migrations']}")
        log.info(f"  Total migrations: {status['total_migrations']}")
        log.info(f"  Is up to date: {status['is_up_to_date']}")
        log.info(f"  Database URL: {status['database_url']}")
        log.info(f"  Backups enabled: {status['backups_enabled']}")
        log.info(f"  Safety checks enabled: {status['safety_checks_enabled']}")

        # Get migration history
        history = manager.get_migration_history()
        log.info(f"\nMigration History ({len(history)} total):")
        for migration in history:
            status_str = "✓ Applied" if migration.is_applied else "○ Pending"
            log.info(f"  {status_str} {migration.revision}: {migration.description}")

        # Get pending migrations
        pending = manager.get_pending_migrations()
        if pending:
            log.info(f"\nPending Migrations ({len(pending)}):")
            for migration in pending:
                log.info(f"  - {migration.revision}: {migration.description}")
        else:
            log.info("\n✓ No pending migrations")

        return manager

    except Exception as e:
        log.error(f"Error in migration status demo: {e}")
        return None


def demo_backup_and_restore(manager):
    """Demonstrate backup and restore functionality."""
    log.info("\n=== Backup and Restore Demo ===")

    try:
        # Create some demo data first
        engine = create_engine_for_url(manager.database_url)
        Base.metadata.create_all(engine)

        with engine.connect() as conn:
            # Insert some sample data if tables exist
            from sqlalchemy import text

            try:
                conn.execute(
                    text(
                        "INSERT OR IGNORE INTO orders (id, token_id, side, price, size, status) "
                        "VALUES ('demo1', 'token1', 'BUY', 0.5, 100, 'FILLED')"
                    )
                )
                conn.commit()
                log.info("✓ Created sample data")
            except Exception:
                log.info("! Could not create sample data (tables may not exist)")

        # Create backup
        log.info("Creating backup...")
        backup_info = manager.create_backup("demo_backup")
        log.info(f"✓ Backup created: {backup_info.backup_path}")
        log.info(f"  Size: {backup_info.size_bytes} bytes")
        log.info(f"  Status: {backup_info.status.value}")

        # Simulate some changes
        with engine.connect() as conn:
            try:
                conn.execute(
                    text(
                        "INSERT OR IGNORE INTO orders (id, token_id, side, price, size, status) "
                        "VALUES ('demo2', 'token2', 'SELL', 0.6, 200, 'OPEN')"
                    )
                )
                conn.commit()
                log.info("✓ Made changes to database")
            except Exception:
                log.info("! Could not modify data")

        # Restore from backup
        log.info("Restoring from backup...")
        manager.restore_backup(backup_info)
        log.info("✓ Database restored from backup")

        return backup_info

    except Exception as e:
        log.error(f"Error in backup/restore demo: {e}")
        return None


def demo_safety_checks(manager):
    """Demonstrate safety check functionality."""
    log.info("\n=== Safety Checks Demo ===")

    try:
        log.info("Running safety checks...")
        manager._perform_safety_checks()
        log.info("✓ All safety checks passed")

        # Validate migration integrity
        log.info("Validating migration integrity...")
        is_valid = manager.validate_migration_integrity()
        if is_valid:
            log.info("✓ Migration integrity check passed")
        else:
            log.warning("! Migration integrity check failed")

    except Exception as e:
        log.error(f"Safety checks failed: {e}")


def demo_backup_cleanup(manager):
    """Demonstrate backup cleanup functionality."""
    log.info("\n=== Backup Cleanup Demo ===")

    try:
        # Create several backups
        log.info("Creating multiple backups for cleanup demo...")
        for i in range(5):
            backup_info = manager.create_backup(f"cleanup_demo_{i}")
            log.info(f"  Created backup {i+1}: {Path(backup_info.backup_path).name}")

        # List backups before cleanup
        backup_files = list(manager.backup_dir.glob("*.sql"))
        log.info(f"Total backups before cleanup: {len(backup_files)}")

        # Clean up old backups
        log.info("Cleaning up old backups (keeping last 3)...")
        removed_count = manager.cleanup_old_backups(keep_last_n=3)
        log.info(f"✓ Removed {removed_count} old backup files")

        # List backups after cleanup
        backup_files = list(manager.backup_dir.glob("*.sql"))
        log.info(f"Total backups after cleanup: {len(backup_files)}")

    except Exception as e:
        log.error(f"Error in backup cleanup demo: {e}")


def demo_auto_rollback(manager):
    """Demonstrate automatic rollback functionality."""
    log.info("\n=== Auto-Rollback Demo ===")

    try:
        # Create a backup point
        backup_info = manager.create_backup("rollback_demo")
        log.info(f"✓ Created rollback point: {Path(backup_info.backup_path).name}")

        # Simulate a failed operation that needs rollback
        log.info("Simulating failed operation requiring rollback...")
        result = manager.auto_rollback(
            backup_info, "Demonstration rollback due to simulated failure"
        )

        if result.success:
            log.info(
                f"✓ Auto-rollback completed successfully in {result.duration_seconds:.2f}s"
            )
            log.info(f"  Status: {result.status.value}")
            log.info(f"  Message: {result.message}")
        else:
            log.error(f"! Auto-rollback failed: {result.message}")

    except Exception as e:
        log.error(f"Error in auto-rollback demo: {e}")


def main():
    """Run all migration system demonstrations."""
    log.info("Migration System Demonstration")
    log.info("==============================")

    try:
        # Demo 1: Check migration status
        manager = demo_migration_status()
        if not manager:
            log.error("Could not initialize migration manager")
            return

        # Demo 2: Backup and restore
        backup_info = demo_backup_and_restore(manager)

        # Demo 3: Safety checks
        demo_safety_checks(manager)

        # Demo 4: Backup cleanup
        demo_backup_cleanup(manager)

        # Demo 5: Auto-rollback
        if backup_info:
            demo_auto_rollback(manager)

        log.info("\n=== Demo Complete ===")
        log.info("All migration system features demonstrated successfully!")

        # Final status
        final_status = manager.get_migration_status()
        log.info("\nFinal Status:")
        log.info(f"  Database: {final_status['database_url']}")
        log.info(f"  Current revision: {final_status['current_revision']}")
        log.info(f"  Up to date: {final_status['is_up_to_date']}")

    except Exception as e:
        log.error(f"Demo failed: {e}")
        raise

    finally:
        # Cleanup demo files
        cleanup_demo_files()


def cleanup_demo_files():
    """Clean up demo files."""
    try:
        demo_files = [Path("demo_migration.db"), Path("demo_backups")]

        for file_path in demo_files:
            if file_path.is_file():
                file_path.unlink()
                log.info(f"Cleaned up: {file_path}")
            elif file_path.is_dir():
                import shutil

                shutil.rmtree(file_path)
                log.info(f"Cleaned up directory: {file_path}")

    except Exception as e:
        log.warning(f"Could not clean up demo files: {e}")


if __name__ == "__main__":
    main()
