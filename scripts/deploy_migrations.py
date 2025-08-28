#!/usr/bin/env python3
"""
Production migration deployment script.
Safely applies database migrations in production environments with comprehensive safety checks.
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
    handlers=[logging.StreamHandler(), logging.FileHandler("migration_deployment.log")],
)
log = logging.getLogger("deploy_migrations")


def confirm_production_deployment() -> bool:
    """Confirm production deployment with user."""
    print("\n" + "=" * 60)
    print("⚠️  PRODUCTION MIGRATION DEPLOYMENT")
    print("=" * 60)
    print("You are about to apply database migrations in production.")
    print("This operation will modify the database schema and may affect")
    print("system availability during the migration process.")
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
    print(f"Environment: {os.environ.get('ENVIRONMENT', 'unknown')}")
    print()

    response = input("Do you want to continue? Type 'YES' to proceed: ")
    return response.strip() == "YES"


def pre_deployment_checks(manager: DatabaseMigrationManager) -> bool:
    """Perform comprehensive pre-deployment checks."""
    log.info("Running pre-deployment checks...")

    try:
        # 1. Validate migration system integrity
        log.info("Checking migration system integrity...")
        if not manager.validate_migration_integrity():
            log.error("Migration system integrity check failed")
            return False
        log.info("✓ Migration system integrity OK")

        # 2. Check migration status
        log.info("Checking migration status...")
        status = manager.get_migration_status()

        log.info(f"Current revision: {status['current_revision']}")
        log.info(f"Pending migrations: {status['pending_migrations']}")

        if status["pending_migrations"] == 0:
            log.info("✓ No pending migrations - database is up to date")
            return True

        # 3. List pending migrations
        pending = manager.get_pending_migrations()
        log.info(f"Pending migrations to apply ({len(pending)}):")
        for migration in pending:
            log.info(f"  - {migration.revision}: {migration.description}")

        # 4. Perform safety checks
        log.info("Running safety checks...")
        manager._perform_safety_checks()
        log.info("✓ Safety checks passed")

        return True

    except Exception as e:
        log.error(f"Pre-deployment checks failed: {e}")
        return False


def deploy_migrations(
    database_url: str | None = None,
    target_revision: str = "head",
    dry_run: bool = False,
    skip_backup: bool = False,
    force: bool = False,
) -> bool:
    """Deploy migrations to production."""

    try:
        # Initialize migration manager
        log.info("Initializing migration manager...")
        manager = DatabaseMigrationManager(
            database_url=database_url,
            enable_backups=not skip_backup,
            enable_safety_checks=True,
        )

        # Production confirmation
        if not force and not dry_run:
            if not confirm_production_deployment():
                log.info("Deployment cancelled by user")
                return False

        # Pre-deployment checks
        if not pre_deployment_checks(manager):
            log.error("Pre-deployment checks failed - aborting deployment")
            return False

        # Check if there are any migrations to apply
        pending = manager.get_pending_migrations()
        if not pending:
            log.info("No migrations to apply - deployment complete")
            return True

        # Dry run mode
        if dry_run:
            log.info("DRY RUN MODE - No actual migrations will be applied")
            log.info(f"Would apply {len(pending)} pending migrations:")
            for migration in pending:
                log.info(f"  - {migration.revision}: {migration.description}")
            return True

        # Apply migrations
        log.info(f"Applying migrations to revision: {target_revision}")
        result = manager.upgrade_to_revision(target_revision)

        if result.success:
            log.info("✓ Migration deployment completed successfully!")
            log.info(f"  Final revision: {result.revision}")
            log.info(f"  Duration: {result.duration_seconds:.2f} seconds")

            if result.backup_info:
                log.info(f"  Backup created: {result.backup_info.backup_path}")

            # Post-deployment verification
            log.info("Running post-deployment verification...")
            final_status = manager.get_migration_status()
            if final_status["is_up_to_date"]:
                log.info("✓ Post-deployment verification passed")
                return True
            else:
                log.warning("! Post-deployment verification shows pending migrations")
                return False
        else:
            log.error(f"✗ Migration deployment failed: {result.message}")

            # Attempt automatic rollback if backup exists
            if result.backup_info and not skip_backup:
                log.info("Attempting automatic rollback...")
                rollback_result = manager.auto_rollback(
                    result.backup_info, "Migration deployment failed"
                )

                if rollback_result.success:
                    log.info("✓ Automatic rollback completed successfully")
                else:
                    log.error(f"✗ Automatic rollback failed: {rollback_result.message}")
                    log.error("CRITICAL: Database may be in inconsistent state!")

            return False

    except MigrationSafetyError as e:
        log.error(f"Migration safety error: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected error during deployment: {e}")
        return False


def main():
    """Main deployment script entry point."""
    parser = argparse.ArgumentParser(
        description="Deploy database migrations to production",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be applied
  python deploy_migrations.py --dry-run
  
  # Deploy all pending migrations
  python deploy_migrations.py
  
  # Deploy to specific revision
  python deploy_migrations.py --target-revision abc123
  
  # Deploy with custom database URL
  python deploy_migrations.py --database-url postgresql://user:pass@host/db
  
  # Skip backup creation (not recommended for production)
  python deploy_migrations.py --skip-backup
  
  # Force deployment without confirmation prompts
  python deploy_migrations.py --force
        """,
    )

    parser.add_argument(
        "--database-url", help="Database URL to use (overrides environment/config)"
    )

    parser.add_argument(
        "--target-revision",
        default="head",
        help="Target revision to migrate to (default: head)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be applied without making changes",
    )

    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip backup creation (NOT recommended for production)",
    )

    parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompts"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Log deployment start
    log.info("=" * 60)
    log.info("PRODUCTION MIGRATION DEPLOYMENT STARTED")
    log.info("=" * 60)
    log.info(f"Target revision: {args.target_revision}")
    log.info(f"Dry run: {args.dry_run}")
    log.info(f"Skip backup: {args.skip_backup}")
    log.info(f"Force: {args.force}")

    try:
        success = deploy_migrations(
            database_url=args.database_url,
            target_revision=args.target_revision,
            dry_run=args.dry_run,
            skip_backup=args.skip_backup,
            force=args.force,
        )

        if success:
            log.info("=" * 60)
            log.info("✓ DEPLOYMENT COMPLETED SUCCESSFULLY")
            log.info("=" * 60)
            sys.exit(0)
        else:
            log.error("=" * 60)
            log.error("✗ DEPLOYMENT FAILED")
            log.error("=" * 60)
            sys.exit(1)

    except KeyboardInterrupt:
        log.warning("Deployment interrupted by user")
        sys.exit(130)
    except Exception as e:
        log.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
