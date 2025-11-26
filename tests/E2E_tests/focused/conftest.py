"""
Increment 8 — Full E2E Test Configuration
Phases 1A (Sync) + Phase 2 (OAuth Provider) + Phase 3 (MCP Integration)

GOALS:
- Use REAL DB + REAL Redis (isolated via env prefix "test:")
- Use REAL sync engine logic (NO internal mocking)
- Use REAL token encryption/decryption
- Use REAL webhook flow & ID semantics
- ONLY mock: Google Calendar HTTP API + Google OAuth token refresh
- Provide deterministic event generation
- Provide time freezing for deterministic timestamp logic
- Provide clean dependency overrides for FastAPI, Redis, Google API, HTTP clients

This file is the SINGLE shared fixture provider for ALL Increment 8 tests:
- test_increment_8_sync.py (Phase 1A)
- test_increment_8_oauth.py (Phase 2)
- test_increment_8_mcp.py (Phase 3)
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any
from unittest.mock import patch, AsyncMock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.database import get_db
from backend.core.redis_client import redis_client
from backend.core.encryption import encrypt_token
from backend.core.models import Base
from backend.apps.focused import db_models  # noqa: F401 - Import models

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://localhost/priority_guardian_test"


# ============================================================================
# E2E Database Fixtures (override parent conftest)
# ============================================================================

@pytest_asyncio.fixture
async def async_engine(setup_test_database):
    """
    Create async engine for E2E test database.

    Overrides parent conftest's async_engine fixture.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        poolclass=NullPool,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """
    Create E2E database session WITHOUT automatic transaction wrapper.

    Unlike the parent conftest which uses `async with session.begin()`,
    this E2E version allows the HTTP handler to manage its own transactions.
    Tests can query the DB after HTTP requests without transaction issues.
    """
    session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_maker() as session:
        yield session

    # Clean up: Truncate all tables after test
    async with async_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE focused_focus_sessions, focused_user_keywords, "
                "core_connections, core_users, oauth_authorization_codes, "
                "oauth_access_tokens RESTART IDENTITY CASCADE"
            )
        )


# ============================================================================
# CRITICAL: FastAPI Dependency Override for Database
# ============================================================================

@pytest.fixture(autouse=True)
def override_db_dependency(async_session: AsyncSession):
    """
    Override get_db to use test session.

    CRITICAL: Without this, all HTTP requests hit the real database.
    This fixture auto-applies to all tests in this conftest scope.
    """
    async def _override():
        yield async_session

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)


# NOTE: Redis uses a singleton pattern (redis_client) with REDIS_ENV_PREFIX
# environment variable for isolation. No FastAPI dependency override needed.
# Tests MUST run with REDIS_ENV_PREFIX="test:" to use isolated keys.


# ============================================================================
# Async Test Client
# ============================================================================

@pytest_asyncio.fixture
async def client(async_session: AsyncSession):
    """
    Async HTTP test client for FastAPI.

    Uses ASGITransport to make requests to the app without running a server.
    The DB override fixture ensures requests use the test session.
    Also initializes app.state.http_client that the sync engine needs.

    Depends on async_session to ensure proper fixture ordering.
    """
    import httpx

    # Initialize the http_client in app state (normally done in lifespan)
    app.state.http_client = httpx.AsyncClient(timeout=30.0)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c

    # Cleanup
    await app.state.http_client.aclose()


# ============================================================================
# MockGoogleCalendar — external Google Calendar API simulation (single source)
# ============================================================================

class MockGoogleCalendar:
    """
    Simulates Google Calendar external API (list_events only).

    Supports:
    - Single page or multi-page responses
    - Error injection (429, 401, network errors)
    - Partial page failures
    - Pagination + race-condition pause
    """

    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self.pages: list[list[dict[str, Any]]] = []
        self.paginated_mode = False
        self.pages_failed = 0
        self.error: Exception | None = None

        # For race-condition test
        self.pause_event: asyncio.Event | None = None
        self.pause_after_page: int | None = None

        self.call_count: int = 0

    def set_events(self, events: list[dict[str, Any]], pages_failed: int = 0):
        """Single-page data."""
        self.events = events
        self.pages_failed = pages_failed
        self.paginated_mode = False
        self.error = None

    def set_paginated_events(self, pages: list[list[dict[str, Any]]], pages_failed: int = 0):
        """Multi-page data."""
        self.pages = pages
        self.pages_failed = pages_failed
        self.paginated_mode = True
        self.error = None

    def inject_error(self, exception: Exception):
        """Raise this exception on next list_events call."""
        self.error = exception

    def enable_pause_after_page(self, page_num: int):
        """Pause sync after page fetch → test race conditions."""
        self.pause_after_page = page_num
        self.pause_event = asyncio.Event()

    async def list_events(
        self,
        http_client,
        access_token: str,
        time_min: str,
        time_max: str,
        max_results_per_page: int = 250,
        max_pages: int = 10,
    ) -> tuple[list[dict[str, Any]], int]:

        self.call_count += 1

        if self.error:
            e = self.error
            self.error = None
            raise e

        if self.paginated_mode:
            all_events = []

            for i, page in enumerate(self.pages, start=1):
                all_events.extend(page)

                # Optional sync pause (race-test)
                if self.pause_after_page == i and self.pause_event:
                    await self.pause_event.wait()

                if i >= max_pages:
                    break

            return all_events, self.pages_failed

        # Single page
        return self.events, self.pages_failed


@pytest.fixture
def mock_google():
    """Fresh Google Calendar mock per test."""
    return MockGoogleCalendar()


# ============================================================================
# MockGoogleWebhook — Google Calendar webhook API simulation
# ============================================================================

class MockGoogleWebhook:
    """
    Simulates Google Calendar webhook API for Phase 1B tests.

    Separate from MockGoogleCalendar to avoid God-object anti-pattern.
    Handles:
    - register_webhook (events.watch)
    - stop_webhook_channel (channels.stop)
    - simulate_webhook (send test webhook to real endpoint)
    """

    def __init__(self):
        self.watch_calls: list[dict[str, Any]] = []
        self.stop_calls: list[dict[str, Any]] = []
        self.active_channels: dict[str, dict[str, Any]] = {}
        self._next_expiration_ms: int | None = None

    def set_next_expiration(self, expires_at: datetime) -> None:
        """Set the expiration for the next register_webhook call."""
        self._next_expiration_ms = int(expires_at.timestamp() * 1000)

    async def register_webhook(
        self,
        http_client,
        access_token: str,
        channel_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """
        Mock for backend.core.google_calendar.register_webhook.

        Returns Google-like response with channel_id, resourceId, expiration.
        """
        # Default: 7 days from now
        if self._next_expiration_ms:
            expiration_ms = self._next_expiration_ms
            self._next_expiration_ms = None  # Reset after use
        else:
            expiration_ms = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000)

        resource_id = f"resource_{channel_id[:8]}"

        self.watch_calls.append({
            "channel_id": channel_id,
            "user_id": user_id,
            "access_token": access_token[:10] + "...",  # Truncated for safety
        })

        self.active_channels[channel_id] = {
            "resource_id": resource_id,
            "expiration_ms": expiration_ms,
            "user_id": user_id,
        }

        return {
            "id": channel_id,
            "resourceId": resource_id,
            "expiration": str(expiration_ms),
        }

    async def stop_webhook_channel(
        self,
        http_client,
        access_token: str,
        channel_id: str,
        resource_id: str,
    ) -> dict:
        """
        Mock for backend.core.google_calendar.stop_webhook_channel.

        Returns dict with success=True if channel existed and was stopped.
        """
        self.stop_calls.append({
            "channel_id": channel_id,
            "resource_id": resource_id,
        })

        if channel_id in self.active_channels:
            del self.active_channels[channel_id]

        # Google returns success even if channel not found
        return {"success": True, "error": None}

    def reset(self) -> None:
        """Reset all state for test isolation."""
        self.watch_calls.clear()
        self.stop_calls.clear()
        self.active_channels.clear()
        self._next_expiration_ms = None


@pytest.fixture
def mock_webhook():
    """Fresh Google webhook mock per test."""
    return MockGoogleWebhook()


@pytest.fixture
def patch_google_webhook(mock_webhook):
    """
    Patch register_webhook and stop_webhook_channel at BOTH import locations.

    The watch_calendar_impl does:
        from backend.core.google_calendar import register_webhook, stop_webhook_channel

    So we must patch at both the definition and import locations.
    """
    with patch(
        "backend.apps.focused.tools.watch_calendar_impl.register_webhook",
        side_effect=mock_webhook.register_webhook
    ), patch(
        "backend.apps.focused.tools.watch_calendar_impl.stop_webhook_channel",
        side_effect=mock_webhook.stop_webhook_channel
    ), patch(
        "backend.core.google_calendar.register_webhook",
        side_effect=mock_webhook.register_webhook
    ), patch(
        "backend.core.google_calendar.stop_webhook_channel",
        side_effect=mock_webhook.stop_webhook_channel
    ):
        yield mock_webhook


# ============================================================================
# Mock event generator
# ============================================================================

class EventFactory:
    """Deterministic factory for valid Google Calendar events."""

    def create(
        self,
        event_id: str,
        summary: str,
        start_time: datetime,
        duration_minutes: int = 60,
        description: str = "",
        status: str = "confirmed",
        updated_at: datetime | None = None,
        ical_uid: str | None = None,
    ) -> dict[str, Any]:
        # Enforce timezone awareness to prevent subtle timestamp bugs
        if start_time.tzinfo is None:
            raise ValueError("EventFactory.create() requires timezone-aware datetime for start_time")
        if updated_at is not None and updated_at.tzinfo is None:
            raise ValueError("EventFactory.create() requires timezone-aware datetime for updated_at")

        end_time = start_time + timedelta(minutes=duration_minutes)
        updated_time = updated_at or start_time

        start_iso = start_time.isoformat().replace("+00:00", "Z")
        end_iso = end_time.isoformat().replace("+00:00", "Z")
        updated_iso = updated_time.isoformat().replace("+00:00", "Z")

        return {
            "kind": "calendar#event",
            "id": event_id,
            "iCalUID": ical_uid or f"{event_id}@google.com",
            "summary": summary,
            "description": description,
            "status": status,
            "updated": updated_iso,
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
        }

    def create_all_day(self, event_id: str, summary: str, date: str):
        return {
            "kind": "calendar#event",
            "id": event_id,
            "iCalUID": f"{event_id}@google.com",
            "summary": summary,
            "status": "confirmed",
            "updated": f"{date}T00:00:00Z",
            "start": {"date": date},
            "end": {"date": date},
        }

    def batch(self, count: int, base: datetime, prefix: str = "evt") -> list[dict[str, Any]]:
        """
        Create multiple events. Alias: create_batch

        Args:
            count: Number of events to create
            base: Base datetime (MUST be timezone-aware)
            prefix: Event ID prefix
        """
        if base.tzinfo is None:
            raise ValueError("EventFactory.batch() requires timezone-aware datetime for base")

        return [
            self.create(
                event_id=f"{prefix}{i}",
                summary=f"Event {i}",
                start_time=base + timedelta(hours=i),
                duration_minutes=60,
                description=f"Description {i}",
            )
            for i in range(count)
        ]

    # Alias for compatibility
    create_batch = batch


@pytest.fixture
def event_factory():
    return EventFactory()


# ============================================================================
# Redis E2E (real Redis used)
# ============================================================================

@pytest_asyncio.fixture(autouse=True)
async def redis_cleanup():
    """
    Ensures Redis is connected and cleans ALL test keys after each test.

    Cleans any key starting with the env prefix (test:, dev:, etc.)
    to cover: focused, oauth, mcp, webhooks, rate limits, etc.
    """
    # CRITICAL SAFETY GUARD: Prevent accidental production data wipe
    assert redis_client._env_prefix.startswith("test:"), \
        "E2E tests MUST run with REDIS_ENV_PREFIX='test:'"

    # Reconnect Redis for each test to avoid event loop issues
    # Close existing connection if any (might be from different event loop)
    if redis_client._client is not None:
        try:
            await redis_client.close()
        except Exception:
            # Ignore errors when closing stale connections
            redis_client._client = None

    # Connect fresh for this test's event loop
    await redis_client.connect()

    yield

    # Clean up ALL keys with env prefix after test
    try:
        if redis_client._client is not None:
            env_prefix = redis_client._env_prefix  # "test:" or "dev:"
            cursor = 0
            keys = []

            while True:
                cursor, batch = await redis_client._client.scan(
                    cursor, match=f"{env_prefix}*", count=100
                )
                keys.extend(batch)
                if cursor == 0:
                    break

            if keys:
                await redis_client._client.delete(*keys)
    except Exception as e:
        # Log but don't fail test on cleanup errors
        import logging
        logging.getLogger(__name__).warning(f"Redis cleanup warning: {e}")


# ============================================================================
# Helper to access real Redis methods (needs_sync, idempotency)
# ============================================================================

@pytest.fixture
def redis_helpers():
    """
    Helper class to access Redis sync functions with correct naming.

    Uses exact function signatures from backend.core.redis_client:
    - get_needs_sync / set_needs_sync / delete_needs_sync
    - check_webhook_idempotency / clear_webhook_idempotency
    - check_renewal_throttle / clear_renewal_throttle
    """
    class RH:
        async def get_needs_sync(self, user_id: str) -> bool:
            from backend.core.redis_client import get_needs_sync
            return await get_needs_sync(user_id)

        async def set_needs_sync(self, user_id: str) -> bool:
            from backend.core.redis_client import set_needs_sync
            return await set_needs_sync(user_id)

        async def delete_needs_sync(self, user_id: str) -> bool:
            from backend.core.redis_client import delete_needs_sync
            return await delete_needs_sync(user_id)

        # Convenience aliases (shorter names for test readability)
        get_needs = get_needs_sync
        set_needs = set_needs_sync
        del_needs = delete_needs_sync

        # Idempotency helpers (Phase 1B)
        async def check_idempotency(self, user_id: str, message_number: str) -> bool:
            """Check if webhook is new (True) or duplicate (False)."""
            from backend.core.redis_client import check_webhook_idempotency
            return await check_webhook_idempotency(user_id, message_number)

        async def clear_idempotency(self, user_id: str, message_number: str) -> bool:
            """Clear idempotency key (for test setup)."""
            from backend.core.redis_client import redis_client
            key = f"focused:webhook:{user_id}:{message_number}"
            result = await redis_client.delete(key)
            return result > 0

        async def has_idempotency_key(self, user_id: str, message_number: str) -> bool:
            """Check if idempotency key exists (without consuming it)."""
            from backend.core.redis_client import redis_client
            key = f"focused:webhook:{user_id}:{message_number}"
            return await redis_client.exists(key) > 0

        # Renewal throttle helpers (Phase 1B)
        # Key format: focused:webhook:renew_throttle:{user_id}
        async def check_throttle(self, user_id: str) -> bool:
            """Check if renewal is allowed (True) or throttled (False)."""
            from backend.core.redis_client import check_renewal_throttle
            return await check_renewal_throttle(user_id)

        async def clear_throttle(self, user_id: str) -> bool:
            """Clear renewal throttle (for test setup)."""
            from backend.core.redis_client import redis_client
            key = f"focused:webhook:renew_throttle:{user_id}"
            result = await redis_client.delete(key)
            return result > 0

        async def has_throttle_key(self, user_id: str) -> bool:
            """Check if throttle key exists."""
            from backend.core.redis_client import redis_client
            key = f"focused:webhook:renew_throttle:{user_id}"
            return await redis_client.exists(key) > 0

        async def get_throttle_ttl(self, user_id: str) -> int:
            """Get TTL of throttle key in seconds (-2 if not exists, -1 if no expiry)."""
            from backend.core.redis_client import redis_client
            key = f"focused:webhook:renew_throttle:{user_id}"
            return await redis_client.ttl(key)

    return RH()


# ============================================================================
# Patch Google Calendar list_events at BOTH import locations
# ============================================================================

@pytest.fixture
def patch_google_list_events(mock_google):
    """
    Patch list_events at BOTH the definition AND import locations.

    The orchestrator does:
        from backend.core.google_calendar import list_events

    So we must patch:
    1. backend.apps.focused.logic.sync.orchestrator.list_events (where it's imported)
    2. backend.core.google_calendar.list_events (the definition, for other imports)

    This ensures ALL sync paths use the mock.
    """
    with patch(
        "backend.apps.focused.logic.sync.orchestrator.list_events",
        side_effect=mock_google.list_events
    ), patch(
        "backend.core.google_calendar.list_events",
        side_effect=mock_google.list_events
    ):
        yield mock_google


# ============================================================================
# override HTTP client (for token refresh, webhook registration)
# ============================================================================

class MockHTTPResponse:
    """Mock HTTP response for async HTTP client."""

    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


@pytest.fixture
def mock_http_client():
    http_client = AsyncMock()

    # POST: Token refresh (default behavior)
    http_client.post.return_value = MockHTTPResponse(200, {
        "access_token": "refreshed_token_999",
        "expires_in": 3600,
    })

    # GET: URL-based routing for OAuth Provider Phase 2
    async def _mock_get(url, *args, **kwargs):
        if "/jwks" in url:
            return MockHTTPResponse(200, {"keys": []})
        if "openid-configuration" in url or ".well-known" in url:
            return MockHTTPResponse(200, {
                "issuer": "http://test",
                "jwks_uri": "http://test/oauth/focused/jwks",
                "authorization_endpoint": "http://test/oauth/focused/authorize",
                "token_endpoint": "http://test/oauth/focused/token",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
            })
        # Default: 404 for unknown GET endpoints
        return MockHTTPResponse(404, {"error": "not_found"})

    http_client.get.side_effect = _mock_get

    return http_client


# NOTE: override_http_client fixture removed - backend.core.http_client module
# does not exist. HTTP client is accessed via app.state.http_client instead.


# ============================================================================
# Test user with REAL encrypted tokens + channel metadata
# ============================================================================

@pytest_asyncio.fixture
async def test_user_with_connection(async_session: AsyncSession):
    user_id = str(uuid4())

    access = f"ya29.access_{user_id[:6]}"
    refresh = f"1//refresh_{user_id[:6]}"

    encrypted_access = encrypt_token(access)
    encrypted_refresh = encrypt_token(refresh)

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    channel_id = f"channel-{uuid4()}"
    resource_id = f"resource-{uuid4()}"
    channel_expires = datetime.now(timezone.utc) + timedelta(days=7)

    await async_session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id},
    )
    await async_session.execute(
        text("""
            INSERT INTO core_connections (
                user_id, provider,
                encrypted_access_token, encrypted_refresh_token,
                token_expires_at, scopes,
                google_channel_id, google_resource_id, google_channel_expires_at
            )
            VALUES (
                :user_id, 'google',
                :access, :refresh,
                :expires, ARRAY['https://www.googleapis.com/auth/calendar.readonly'],
                :channel, :resource, :channel_exp
            )
        """),
        {
            "user_id": user_id,
            "access": encrypted_access,
            "refresh": encrypted_refresh,
            "expires": expires,
            "channel": channel_id,
            "resource": resource_id,
            "channel_exp": channel_expires,
        },
    )
    await async_session.flush()

    return {
        "user_id": user_id,
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": expires,
        "channel_id": channel_id,
        "resource_id": resource_id,
        "channel_expires_at": channel_expires,
    }


# ============================================================================
# Test user WITHOUT channel (for fresh registration tests)
# ============================================================================

@pytest_asyncio.fixture
async def test_user_without_channel(async_session: AsyncSession):
    """
    Creates a user with OAuth connection but NO webhook channel.

    Use this for testing fresh webhook registration (Test 01).
    """
    user_id = str(uuid4())

    access = f"ya29.access_{user_id[:6]}"
    refresh = f"1//refresh_{user_id[:6]}"

    encrypted_access = encrypt_token(access)
    encrypted_refresh = encrypt_token(refresh)

    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    await async_session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id},
    )
    await async_session.execute(
        text("""
            INSERT INTO core_connections (
                user_id, provider,
                encrypted_access_token, encrypted_refresh_token,
                token_expires_at, scopes
            )
            VALUES (
                :user_id, 'google',
                :access, :refresh,
                :expires, ARRAY['https://www.googleapis.com/auth/calendar.readonly']
            )
        """),
        {
            "user_id": user_id,
            "access": encrypted_access,
            "refresh": encrypted_refresh,
            "expires": expires,
        },
    )
    await async_session.flush()

    return {
        "user_id": user_id,
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": expires,
    }


# ============================================================================
# Time freezing
# ============================================================================

@pytest.fixture
def freeze_time():
    """
    Provides freezegun's freeze_time for deterministic timestamp tests.

    IMPORTANT: Always use UTC timezone suffix to avoid local timezone issues:
        with freeze_time("2025-01-01 00:00:00 UTC"):
            ...

    Falls back to a no-op context manager if freezegun is not installed.
    """
    try:
        from freezegun import freeze_time as ft
        return ft
    except ImportError:
        from contextlib import contextmanager
        @contextmanager
        def noop(_): yield
        return noop


# ============================================================================
# Assertion helper
# ============================================================================

@pytest.fixture
def assert_event_in_db():
    async def _assert(
        session: AsyncSession,
        user_id: str,
        event_id: str,
        **expected
    ):
        from backend.apps.focused.db_models import FocusedFocusSession
        from sqlalchemy import select

        session.expire_all()
        stmt = select(FocusedFocusSession).where(
            FocusedFocusSession.user_id == user_id,
            FocusedFocusSession.google_event_id == event_id,
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        assert row, f"Event {event_id} missing"

        for k, v in expected.items():
            assert getattr(row, k) == v, f"{event_id}.{k}: expected {v}, got {getattr(row, k)}"

    return _assert
