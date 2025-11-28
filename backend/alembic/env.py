"""Alembic environment configuration for async migrations."""

import asyncio #to run async code from a sync entrypoint (Alembic)
from logging.config import fileConfig #sets up logging from alembic.ini

from sqlalchemy import pool #to use NullPool (no pooling) for migrations.
from sqlalchemy.engine import Connection #typing hint for a DB connection.
from sqlalchemy.ext.asyncio import async_engine_from_config #builds an async SQLAlchemy engine using settings from alembic.ini.

from alembic import context #main Alembic API (gives you migration context, config, offline/online mode, etc.).

# Import Base for autogenerate support
from backend.core.models import Base #your SQLAlchemy ORM base. Alembic uses Base.metadata to know which tables/columns exist → for --autogenerate
from backend.core.config import settings #your Pydantic config, so Alembic can read DATABASE_URL from the same source as your app. This keeps migrations and app pointed at the same DB.

# Import all models so Alembic can see them for autogenerate
from backend.apps.focused import db_models  # noqa: F401

# Alembic Config object.This is how you access config options like sqlalchemy.url.
config = context.config

# Overrides whatever is in alembic.ini with your real DB URL from .env via settings 
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging for debugging migrations
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata #


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

#This is the function that actually executes migrations against a live DB, given a DB connection
def do_run_migrations(connection: Connection) -> None:
    """Run migrations with given connection."""
    context.configure(connection=connection, target_metadata=target_metadata) #an open SQLAlchemy connection (sync at this level). binds Alembic to that connection and metadata.

    with context.begin_transaction(): #wraps migration operations in a transaction.
        context.run_migrations() #executes upgrade/downgrade steps.


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    connectable = async_engine_from_config( #builds an async engine from alembic.ini settings (which now include your settings.DATABASE_URL).
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
#This is how you marry async SQLAlchemy with Alembic, which is still largely sync-first.
    async with connectable.connect() as connection: #opens an async connection.
        await connection.run_sync(do_run_migrations) #Alembic's do_run_migrations expects a sync Connection.run_sync lets you run sync code safely with an async connection.

    await connectable.dispose() #clean up the engine (close connections)

#lets the sync Alembic CLI run async DB logic. → this function is triggered → runs async engine → applies migrations.
def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Check if a connection was passed in (for testing)
    connectable = config.attributes.get("connection", None)

    if connectable is not None:
        # Use the provided connection (for integration tests)
        do_run_migrations(connectable)
    else:
        # Normal async mode - create engine from config
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
