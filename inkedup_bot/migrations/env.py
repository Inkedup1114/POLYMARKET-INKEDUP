"""
Alembic environment configuration for database migrations.
Handles both online and offline migration modes with proper configuration loading.
"""

import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from inkedup_bot.config import BotConfig

# Import all models to ensure they're registered with Base.metadata
from inkedup_bot.db_models import (
    Base,
    create_engine_for_url,
    get_database_url,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_database_url_for_migrations() -> str:
    """Get database URL for migrations from various sources."""
    # 1. Check environment variable
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        logger.info("Using DATABASE_URL from environment")
        return get_database_url(db_url)

    # 2. Check Alembic config
    db_url = config.get_main_option("sqlalchemy.url")
    if db_url and db_url.strip():
        logger.info("Using database URL from alembic.ini")
        return get_database_url(db_url)

    # 3. Load from bot configuration
    try:
        bot_config = BotConfig()
        db_url = bot_config.database_url
        logger.info(f"Using database URL from BotConfig: {db_url}")
        return get_database_url(db_url)
    except Exception as e:
        logger.warning(f"Could not load BotConfig: {e}")

    # 4. Fallback to default SQLite
    default_url = "sqlite:///bot_data.db"
    logger.info(f"Using default database URL: {default_url}")
    return get_database_url(default_url)


def include_name(name, type_, parent_names):
    """
    Filter function to control which database objects are included in migrations.
    """
    # Skip temporary tables and internal SQLite tables
    if type_ == "table" and name.startswith(("temp_", "sqlite_")):
        return False

    # Include all other tables and objects
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url_for_migrations()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # Enable batch mode for SQLite
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    database_url = get_database_url_for_migrations()

    # Create engine using our helper function
    connectable = create_engine_for_url(
        database_url,
        poolclass=pool.NullPool,  # Disable pooling for migrations
        echo=False,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,  # Enable batch mode for SQLite
        )

        with context.begin_transaction():
            context.run_migrations()


def run_async_migrations() -> None:
    """Run migrations in async mode for async database engines."""
    # This would be used if we had async SQLAlchemy models
    # For now, we use synchronous migrations even with async connection pools
    run_migrations_online()


if context.is_offline_mode():
    logger.info("Running migrations in offline mode")
    run_migrations_offline()
else:
    logger.info("Running migrations in online mode")
    run_migrations_online()
