"""
Integration test configuration.

Extends base conftest with fixtures specific to integration tests.
"""

import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def async_session_with_alembic(async_session):
    """
    Create async session with alembic_version table populated.

    The test database uses Base.metadata.create_all() which doesn't create
    the alembic_version table (that's managed by Alembic). This fixture
    creates it for tests that need to validate schema including alembic state.
    """
    # Create alembic_version table if it doesn't exist
    await async_session.execute(
        text("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
        """)
    )

    # Insert a test revision (clear first in case of previous test)
    await async_session.execute(text("DELETE FROM alembic_version"))
    await async_session.execute(
        text("INSERT INTO alembic_version (version_num) VALUES ('test_revision_abc123')")
    )
    await async_session.commit()

    yield async_session

    # Cleanup - drop the table after test
    await async_session.execute(text("DROP TABLE IF EXISTS alembic_version"))
    await async_session.commit()
