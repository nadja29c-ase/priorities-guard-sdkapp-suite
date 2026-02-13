"""
Test configuration for all test suites.

Provides async database fixtures and test client for testing.
Merged from oauth_provider/conftest.py and focused/conftest.py.
conftest.py provides unit-test-level DB fixtures:
- local ephemeral async engine
- auto-rollback per test
- table truncation
- fakeredis for Redis tests
- no HTTP client state
- no external service mocking

This is your standard test harness for:
- Unit tests
- Integration tests that dont involve Google, Redis, OAuth, MCP
- Pure DB logic tests
- Token encryption tests
- OAuth validator unit tests
- Business logic tests that dont require real HTTP
- OAuth rate limiting tests (with fakeredis)

"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text, create_engine
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.models import Base
from backend.apps.focused import db_models  # noqa: F401 - Import models so they're registered with Base
from backend.apps.clarity import db_models as clarity_db_models  # noqa: F401 - Import Clarity models
from backend.apps.priority_guardian import db_models as pg_db_models  # noqa: F401 - Import PG models
from backend.core.oauth_provider import models as oauth_models  # noqa: F401 - Import OAuth models

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
    # Order matters for FK constraints: snapshot tables before priorities
    async with async_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE focused_focus_sessions, focused_user_keywords, "
                "focused_scheduled_jobs, clarity_clusters, "
                "pg_weekly_snapshots, pg_weekly_overview, pg_deliverables, pg_priorities, "
                "core_connections, core_users, core_tool_audit_log, core_consents, "
                "oauth_authorization_codes, oauth_access_tokens, oauth_state "
                "RESTART IDENTITY CASCADE"
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


# =============================================================================
# FAKEREDIS FIXTURE (for rate limiting and Redis-dependent tests)
# =============================================================================

class FakeRedisClient:
    """
    Fake Redis client for testing rate limiting and caching.

    Mimics the RedisClient interface from backend/core/redis_client.py
    with in-memory storage for isolation between tests.
    """

    def __init__(self, env_prefix: str = "test:"):
        self._storage: dict = {}
        self._ttls: dict = {}
        self._env_prefix = env_prefix
        self._client = self  # For compatibility with rate_limit.py accessing _client.expire

    def _prefix_key(self, key: str) -> str:
        return f"{self._env_prefix}{key}"

    def is_connected(self) -> bool:
        return True

    async def get(self, key: str):
        prefixed = self._prefix_key(key)
        return self._storage.get(prefixed)

    async def set(self, key: str, value, ex: int = None, nx: bool = False):
        prefixed = self._prefix_key(key)

        if nx and prefixed in self._storage:
            return None  # Key exists, NX prevents set

        self._storage[prefixed] = value
        if ex:
            self._ttls[prefixed] = ex
        return True

    async def delete(self, key: str) -> int:
        prefixed = self._prefix_key(key)
        if prefixed in self._storage:
            del self._storage[prefixed]
            self._ttls.pop(prefixed, None)
            return 1
        return 0

    async def incr(self, key: str, amount: int = 1):
        prefixed = self._prefix_key(key)
        current = self._storage.get(prefixed, 0)
        if isinstance(current, str):
            current = int(current)
        new_value = current + amount
        self._storage[prefixed] = new_value
        return new_value

    async def incrby(self, key: str, amount: int = 1):
        """Alias for incr (compatibility with redis.asyncio)."""
        return await self.incr(key, amount)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on key (for rate limiting compatibility)."""
        prefixed = self._prefix_key(key)
        if prefixed in self._storage:
            self._ttls[prefixed] = seconds
            return True
        return False

    async def exists(self, key: str) -> int:
        prefixed = self._prefix_key(key)
        return 1 if prefixed in self._storage else 0

    async def ttl(self, key: str) -> int:
        prefixed = self._prefix_key(key)
        if prefixed not in self._storage:
            return -2
        return self._ttls.get(prefixed, -1)

    def keys(self, pattern: str = "*") -> list:
        """
        Return all keys matching pattern (simple implementation).

        For testing, returns all keys if pattern is "*" or contains "*".
        Otherwise returns exact match.
        """
        if "*" in pattern:
            # Simple wildcard: return all keys (strip prefix for external view)
            prefix_len = len(self._env_prefix)
            return [k[prefix_len:] for k in self._storage.keys()]
        else:
            prefixed = self._prefix_key(pattern)
            if prefixed in self._storage:
                return [pattern]
            return []

    def advance_time(self, seconds: int) -> None:
        """
        Simulate passage of time by reducing TTLs and expiring keys.

        Args:
            seconds: Number of seconds to advance

        Keys with TTL <= 0 after advancement are deleted.
        This allows testing rate limit TTL expiration.
        """
        expired_keys = []

        for prefixed_key, ttl in list(self._ttls.items()):
            new_ttl = ttl - seconds
            if new_ttl <= 0:
                expired_keys.append(prefixed_key)
            else:
                self._ttls[prefixed_key] = new_ttl

        # Delete expired keys
        for key in expired_keys:
            self._storage.pop(key, None)
            self._ttls.pop(key, None)

    def clear(self):
        """Clear all stored data (call between tests)."""
        self._storage.clear()
        self._ttls.clear()


@pytest.fixture
def fake_redis():
    """
    Provide a FakeRedisClient for testing.

    Use this fixture for unit tests that need Redis mocking.
    For integration tests that need Redis injected into the app,
    use fake_redis_client instead.
    """
    return FakeRedisClient()


@pytest_asyncio.fixture
async def fake_redis_client():
    """
    Patch the global redis_client with FakeRedisClient for integration tests.

    This patches backend.core.redis_client.redis_client so that
    rate limiting, authorization context, and other Redis-dependent code uses the fake.
    Automatically clears storage between tests.
    """
    fake = FakeRedisClient()

    with patch("backend.core.redis_client.redis_client", fake):
        with patch("backend.core.rate_limit.redis_client", fake):
            with patch("backend.core.oauth_provider.services.authorization_service.redis_client", fake):
                yield fake

    fake.clear()
