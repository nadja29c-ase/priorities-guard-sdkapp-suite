"""
Test configuration for all test suites.

Provides async database fixtures and test client for testing.
Merged from oauth_provider/conftest.py and focused/conftest.py.
conftest.py provides unit-test-level DB fixtures:
- local ephemeral async engine
- auto-rollback per test
- table truncation
- no real Redis
- no HTTP client state
- no external service mocking

This is your standard test harness for:
- Unit tests
- Integration tests that dont involve Google, Redis, OAuth, MCP
- Pure DB logic tests
- Token encryption tests
- OAuth validator unit tests
- Business logic tests that dont require real HTTP

"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text, create_engine
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport

from backend.core.models import Base
from backend.apps.focused import db_models  # noqa: F401 - Import models so they're registered with Base

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://localhost/priority_guardian_test"
TEST_DATABASE_URL_SYNC = "postgresql+psycopg://localhost/priority_guardian_test"


# =============================================================================
# SESSION-SCOPED FIXTURES (run once per test session)
# =============================================================================

@pytest.fixture(scope="session")
def setup_test_database():
    """
    Set up test database schema from SQLAlchemy models.

    Runs once per test session. Creates all tables from Base.metadata.
    """
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


# =============================================================================
# FUNCTION-SCOPED FIXTURES (run for each test)
# =============================================================================

@pytest_asyncio.fixture
async def async_engine(setup_test_database):
    """
    Create async engine for test database (one per test for complete isolation).

    Uses NullPool to avoid connection pooling in tests.
    """
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

    For integration tests: No outer transaction wrapper. The endpoint
    commits its own transactions normally. Isolation is achieved via
    TRUNCATE in the cleanup_db fixture.
    """
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        # Session closes normally - no rollback needed


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db(async_engine):
    """
    Truncate all tables after each test for isolation.

    This runs automatically after every test (autouse=True).
    """
    yield  # Let the test run first

    # Clean up: Truncate all tables after test
    async with async_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE focused_focus_sessions, focused_user_keywords, "
                "focused_scheduled_jobs, core_connections, core_users, "
                "core_tool_audit_log RESTART IDENTITY CASCADE"
            )
        )


@pytest_asyncio.fixture
async def client(async_engine):
    """
    Create async test client with database dependency override.

    This ensures the FastAPI app uses the test database instead of production.
    The endpoint gets its own session that can commit independently.
    Test fixtures use a separate async_session for setup/verification.
    """
    import httpx
    from backend.main import app
    from backend.core.database import get_db

    # Create session maker for endpoint's sessions
    endpoint_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Override get_db to give endpoint its own session (can commit normally)
    async def override_get_db():
        async with endpoint_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Set up app.state.http_client (normally done in lifespan)
    app.state.http_client = httpx.AsyncClient(timeout=30.0)

    # Create async test client
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as test_client:
        yield test_client

    # Clean up
    await app.state.http_client.aclose()
    app.dependency_overrides.clear()
