#!/usr/bin/env python3
"""
Production migration rollback script.
Safely rolls back database migrations in production environments.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inkedup_bot.migration_manager import DatabaseMigrationManager, MigrationSafetyError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("migration_rollback.log")],
)
log = logging.getLogger("rollback_migrations")


def confirm_production_rollback(target_revision: str) -> bool:
    """Confirm production rollback with user."""
    print("\n" + "=" * 60)
    print("⚠️  PRODUCTION MIGRATION ROLLBACK")
    print("=" * 60)
    print("You are about to ROLLBACK database migrations in production.")
    print("This is a potentially destructive operation that may result in")
    print("DATA LOSS if the migrations being rolled back contain data changes.")
    print()

    # Show environment info
    database_url = os.environ.get("DATABASE_URL", "Not set")
    if "@" in database_url:
        # Hide credentials in display
        parts = database_url.split("@")
        clean_url = f"{parts[0].split('://')[0]}://***@{parts[1]}"
    else:
        clean_url = database_url

    print(f"Target Database: {clean_url}")
    print(f"Target Revision: {target_revision}")
    print(f"Environment: {os.environ.get('ENVIRONMENT', 'unknown')}")
    print()
    print("⚠️  WARNING: This operation may cause data loss!")
    print()

    response = input(
        "Are you absolutely sure you want to proceed? Type 'YES I UNDERSTAND' to continue: "
    )
    return response.strip() == "YES I UNDERSTAND"


def show_rollback_plan(manager: DatabaseMigrationManager, target_revision: str):
    """Show what migrations will be rolled back."""
    log.info("Analyzing rollback plan...")

    try:
        current_rev = manager.get_current_revision()
        history = manager.get_migration_history()

        log.info(f"Current revision: {current_rev}")
        log.info(f"Target revision: {target_revision}")

        # Find migrations that will be rolled back
        rollback_migrations = []
        found_current = False
        found_target = False

        for migration in reversed(history):
            if migration.revision == current_rev:
                found_current = True
                continue

            if found_current and not found_target:
                if migration.revision == target_revision:
                    found_target = True
                    break
                rollback_migrations.append(migration)

        if rollback_migrations:
            log.warning(
                f"The following {len(rollback_migrations)} migration(s) will be ROLLED BACK:"
            )
            for migration in rollback_migrations:
                log.warning(f"  - {migration.revision}: {migration.description}")
            log.warning("⚠️  Any data changes made by these migrations may be LOST!")
        else:
            log.info(
                "No migrations will be rolled back (already at or past target revision)"
            )

        return rollback_migrations

    except Exception as e:
        log.error(f"Error analyzing rollback plan: {e}")
        return []


def rollback_migrations(
    target_revision: str,
    database_url: str | None = None,
    dry_run: bool = False,
    skip_backup: bool = False,
    force: bool = False,
) -> bool:
    """Rollback migrations to target revision."""

    try:
        # Initialize migration manager
        log.info("Initializing migration manager...")
        manager = DatabaseMigrationManager(
            database_url=database_url,
            enable_backups=not skip_backup,
            enable_safety_checks=True,
        )

        # Show rollback plan
        rollback_migrations_list = show_rollback_plan(manager, target_revision)

        if not rollback_migrations_list:
            log.info("No rollback needed - already at or past target revision")
            return True

        # Production confirmation
        if not force and not dry_run:
            if not confirm_production_rollback(target_revision):
                log.info("Rollback cancelled by user")
                return False

        # Safety checks
        log.info("Running safety checks...")
        try:
            manager._perform_safety_checks()
            log.info("✓ Safety checks passed")
        except Exception as e:
            log.error(f"Safety checks failed: {e}")
            if not force:
                log.error("Aborting rollback due to failed safety checks")
                return False
            log.warning("Proceeding despite failed safety checks (--force specified)")

        # Dry run mode
        if dry_run:
            log.info("DRY RUN MODE - No actual rollback will be performed")
            log.info(
                f"Would rollback {len(rollback_migrations_list)} migrations to revision: {target_revision}"
            )
            return True

        # Perform rollback
        log.info(f"Starting rollback to revision: {target_revision}")
        result = manager.downgrade_to_revision(target_revision)

        if result.success:
            log.info("✓ Migration rollback completed successfully!")
            log.info(f"  Current revision: {result.revision}")
            log.info(f"  Duration: {result.duration_seconds:.2f} seconds")

            if result.backup_info:
                log.info(f"  Backup created: {result.backup_info.backup_path}")

            # Post-rollback verification
            log.info("Running post-rollback verification...")
            final_status = manager.get_migration_status()
            if final_status["current_revision"] == target_revision:
                log.info("✓ Post-rollback verification passed")
                return True
            else:
                log.error(
                    f"! Post-rollback verification failed: expected {target_revision}, got {final_status['current_revision']}"
                )
                return False
        else:
            log.error(f"✗ Migration rollback failed: {result.message}")

            # Show error details
            if result.error_details:
                log.error(f"Error details: {result.error_details}")

            return False

    except MigrationSafetyError as e:
        log.error(f"Migration safety error: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected error during rollback: {e}")
        return False


def list_available_revisions(database_url: str | None = None):
    """List available revisions for rollback."""
    try:
        manager = DatabaseMigrationManager(database_url=database_url)
        current_rev = manager.get_current_revision()
        history = manager.get_migration_history()

        print(f"\nCurrent revision: {current_rev}")
        print("\nAvailable revisions for rollback:")
        print("-" * 60)

        for migration in reversed(history):
            status = (
                "CURRENT"
                if migration.revision == current_rev
                else "APPLIED" if migration.is_applied else "NOT APPLIED"
            )
            print(
                f"{migration.revision[:8]}... | {status:12} | {migration.description}"
            )

    except Exception as e:
        log.error(f"Error listing revisions: {e}")


def main():
    """Main rollback script entry point."""
    parser = argparse.ArgumentParser(
        description="Rollback database migrations in production",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available revisions
  python rollback_migrations.py --list-revisions
  
  # Dry run rollback to specific revision
  python rollback_migrations.py abc123 --dry-run
  
  # Rollback to specific revision
  python rollback_migrations.py abc123
  
  # Rollback with custom database URL
  python rollback_migrations.py abc123 --database-url postgresql://user:pass@host/db
  
  # Force rollback without confirmation
  python rollback_migrations.py abc123 --force
        """,
    )

    parser.add_argument(
        "target_revision", nargs="?", help="Target revision to rollback to"
    )

    parser.add_argument(
        "--database-url", help="Database URL to use (overrides environment/config)"
    )

    parser.add_argument(
        "--list-revisions",
        action="store_true",
        help="List available revisions and exit",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be rolled back without making changes",
    )

    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip backup creation (NOT recommended for production)",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts and safety checks",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle list revisions
    if args.list_revisions:
        list_available_revisions(args.database_url)
        sys.exit(0)

    # Validate arguments
    if not args.target_revision:
        parser.error(
            "target_revision is required (use --list-revisions to see available revisions)"
        )

    # Log rollback start
    log.info("=" * 60)
    log.info("PRODUCTION MIGRATION ROLLBACK STARTED")
    log.info("=" * 60)
    log.info(f"Target revision: {args.target_revision}")
    log.info(f"Dry run: {args.dry_run}")
    log.info(f"Skip backup: {args.skip_backup}")
    log.info(f"Force: {args.force}")

    try:
        success = rollback_migrations(
            target_revision=args.target_revision,
            database_url=args.database_url,
            dry_run=args.dry_run,
            skip_backup=args.skip_backup,
            force=args.force,
        )

        if success:
            log.info("=" * 60)
            log.info("✓ ROLLBACK COMPLETED SUCCESSFULLY")
            log.info("=" * 60)
            sys.exit(0)
        else:
            log.error("=" * 60)
            log.error("✗ ROLLBACK FAILED")
            log.error("=" * 60)
            sys.exit(1)

    except KeyboardInterrupt:
        log.warning("Rollback interrupted by user")
        sys.exit(130)
    except Exception as e:
        log.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
