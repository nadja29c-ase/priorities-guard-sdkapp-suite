"""
Test configuration for Focused app tests.

Provides async database fixtures for testing.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text, create_engine
from sqlalchemy.pool import NullPool

from backend.core.models import Base
from backend.apps.focused import db_models  # noqa: F401 - Import models so they're registered with Base

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://localhost/priority_guardian_test"
TEST_DATABASE_URL_SYNC = "postgresql+psycopg://localhost/priority_guardian_test"


@pytest.fixture(scope="session")
def setup_test_database():
    """Set up test database schema from SQLAlchemy models."""
    # Create sync engine
    sync_engine = create_engine(TEST_DATABASE_URL_SYNC, poolclass=NullPool)

    # Clean slate: drop all tables and ENUM types
    Base.metadata.drop_all(sync_engine)

    # Manually drop ENUM types that might be left over
    with sync_engine.connect() as conn:
        conn.execute(text("DROP TYPE IF EXISTS event_status_enum CASCADE"))
        conn.commit()

    # Create all tables from models (this will also create ENUM types)
    Base.metadata.create_all(sync_engine)

    sync_engine.dispose()

    yield

    # Cleanup after all tests
    sync_engine = create_engine(TEST_DATABASE_URL_SYNC, poolclass=NullPool)
    Base.metadata.drop_all(sync_engine)
    with sync_engine.connect() as conn:
        conn.execute(text("DROP TYPE IF EXISTS event_status_enum CASCADE"))
        conn.commit()
    sync_engine.dispose()


@pytest_asyncio.fixture
async def async_engine(setup_test_database):
    """Create async engine for test database (one per test for complete isolation)."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        poolclass=NullPool,  # No connection pooling for tests
    )

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """
    Create a new database session for each test.

    Complete isolation: Each test gets its own engine and session.
    """
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session

    # Clean up: Truncate all tables after test
    async with async_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE focused_focus_sessions, focused_user_keywords, core_connections, core_users RESTART IDENTITY CASCADE"))
