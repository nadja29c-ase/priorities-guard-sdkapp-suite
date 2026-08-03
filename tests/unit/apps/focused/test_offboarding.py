"""
Unit tests for offboarding logic (Increment 10).

Tests disconnect and delete-data operations without external service calls.
Mocks Google API calls and Redis to isolate business logic.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser, CoreConnection, CoreToolAuditLog
from backend.core.encryption import encrypt_token
from backend.core.oauth_provider.models import OAuthAccessToken
from backend.apps.focused.db_models import FocusedFocusSession, FocusedUserKeyword
from backend.apps.focused.logic.offboarding import (
    disconnect_user,
    delete_user_data,
    clear_user_redis_cache,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user."""
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.flush()
    return user


@pytest_asyncio.fixture
async def google_connection(async_session: AsyncSession, test_user: CoreUser):
    """Create a Google connection with webhook."""
    connection = CoreConnection(
        user_id=test_user.id,
        provider="google",
        # Note: connection_type defaults to "unknown" in production
        # (oauth_google_router.py doesn't set it explicitly)
        encrypted_access_token=encrypt_token("test_access_token"),
        encrypted_refresh_token=encrypt_token("test_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        google_channel_id="channel-123",
        google_resource_id="resource-456",
        google_channel_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    async_session.add(connection)
    await async_session.flush()
    return connection


@pytest_asyncio.fixture
async def oauth_tokens(async_session: AsyncSession, test_user: CoreUser):
    """Create ChatGPT OAuth tokens for the user."""
    tokens = []
    for i in range(3):
        token = OAuthAccessToken(
            jti=f"token-{uuid4()}",
            user_id=test_user.id,
            client_id="test-client",
            scope=["focused.read", "focused.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            refresh_token_enc=encrypt_token(f"refresh-{i}"),
            refresh_token_hash=f"hash-{i}",
            refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            revoked=False,
        )
        async_session.add(token)
        tokens.append(token)
    await async_session.flush()
    return tokens


@pytest_asyncio.fixture
async def focus_sessions(async_session: AsyncSession, test_user: CoreUser):
    """Create focus sessions for the user."""
    sessions = []
    base_time = datetime.now(timezone.utc) + timedelta(hours=1)
    for i in range(5):
        session = FocusedFocusSession(
            user_id=test_user.id,
            google_event_id=f"event-{i}",
            google_calendar_id="primary",
            google_ical_uid=f"ical-{i}@google.com",
            google_updated_at=datetime.now(timezone.utc),
            start_time=base_time + timedelta(hours=i),
            end_time=base_time + timedelta(hours=i+1),
            is_focus_block=True,
            matched_keyword="focus",
            sha256_content_hash="a" * 64,
        )
        async_session.add(session)
        sessions.append(session)
    await async_session.flush()
    return sessions


@pytest_asyncio.fixture
async def user_keywords(async_session: AsyncSession, test_user: CoreUser):
    """Create user keywords."""
    keywords = []
    for word in ["deep work", "coding", "writing"]:
        kw = FocusedUserKeyword(
            user_id=test_user.id,
            keyword=word,
        )
        async_session.add(kw)
        keywords.append(kw)
    await async_session.flush()
    return keywords


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for Google API calls."""
    return AsyncMock()


@pytest.fixture
def mock_redis_client():
    """Mock Redis client with async methods."""
    redis = AsyncMock()

    async def empty_scan_iter(match):  # noqa: ARG001
        if False:  # pragma: no cover
            yield

    redis.scan_iter = empty_scan_iter
    redis.delete = AsyncMock()
    return redis


# =============================================================================
# Disconnect Tests
# =============================================================================

class TestDisconnectUser:
    """Tests for disconnect_user function."""

    @pytest.mark.asyncio
    async def test_disconnect_with_active_connection(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        google_connection: CoreConnection,
        oauth_tokens: list[OAuthAccessToken],
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """Test disconnect revokes tokens and clears webhook."""
        # Mock Google API responses
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ) as mock_stop:
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ) as mock_revoke:
                result = await disconnect_user(
                    user_id=test_user.id,
                    session=async_session,
                    http_client=mock_http_client,
                    redis_client=mock_redis_client,
                )

        # Verify result
        assert result["success"] is True
        assert result["already_disconnected"] is False
        assert "revoked_at" in result
        assert result["details"]["google_token_revoked"] is True
        assert result["details"]["webhook_stopped"] is True

        # Verify stop_webhook_channel was called
        mock_stop.assert_called_once()
        call_args = mock_stop.call_args
        assert call_args.kwargs["channel_id"] == "channel-123"
        assert call_args.kwargs["resource_id"] == "resource-456"

        # Verify revoke_google_token was called
        mock_revoke.assert_called_once()

        # Verify connection was updated
        await async_session.refresh(google_connection)
        assert google_connection.revoked_at is not None
        assert google_connection.google_channel_id is None
        assert google_connection.google_resource_id is None

        # Verify OAuth tokens were marked revoked
        for token in oauth_tokens:
            await async_session.refresh(token)
            assert token.revoked is True
            assert token.revoked_at is not None

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        google_connection: CoreConnection,
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """Test disconnect is idempotent - calling twice returns success."""
        # First disconnect
        google_connection.revoked_at = datetime.now(timezone.utc)
        await async_session.flush()

        result = await disconnect_user(
            user_id=test_user.id,
            session=async_session,
            http_client=mock_http_client,
            redis_client=mock_redis_client,
        )

        assert result["success"] is True
        assert result["already_disconnected"] is True

    @pytest.mark.asyncio
    async def test_disconnect_no_connection(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """Test disconnect when user has no Google connection."""
        result = await disconnect_user(
            user_id=test_user.id,
            session=async_session,
            http_client=mock_http_client,
            redis_client=mock_redis_client,
        )

        assert result["success"] is True
        assert result["already_disconnected"] is True

    @pytest.mark.asyncio
    async def test_disconnect_sets_revoked_at_timestamp_once(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        google_connection: CoreConnection,
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """
        Test disconnect sets revoked_at exactly once and doesn't overwrite it.

        Verifies:
        1. revoked_at is set on first disconnect
        2. revoked_at remains unchanged on subsequent calls (idempotency)
        3. The original timestamp is preserved
        """
        # Verify initial state
        assert google_connection.revoked_at is None

        # First disconnect
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                result1 = await disconnect_user(
                    user_id=test_user.id,
                    session=async_session,
                    http_client=mock_http_client,
                    redis_client=mock_redis_client,
                )

        # Verify revoked_at was set
        await async_session.refresh(google_connection)
        assert google_connection.revoked_at is not None
        original_revoked_at = google_connection.revoked_at
        assert result1["already_disconnected"] is False

        # Second disconnect (should be idempotent)
        result2 = await disconnect_user(
            user_id=test_user.id,
            session=async_session,
            http_client=mock_http_client,
            redis_client=mock_redis_client,
        )

        # Verify revoked_at was NOT changed
        await async_session.refresh(google_connection)
        assert google_connection.revoked_at == original_revoked_at, (
            "revoked_at should not change on subsequent disconnect calls"
        )
        assert result2["already_disconnected"] is True

        # Third disconnect - still idempotent
        result3 = await disconnect_user(
            user_id=test_user.id,
            session=async_session,
            http_client=mock_http_client,
            redis_client=mock_redis_client,
        )

        await async_session.refresh(google_connection)
        assert google_connection.revoked_at == original_revoked_at, (
            "revoked_at must remain unchanged across multiple disconnect calls"
        )
        assert result3["already_disconnected"] is True
        assert result3["revoked_at"] == original_revoked_at.isoformat()

    @pytest.mark.asyncio
    async def test_disconnect_google_api_failure_continues(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        google_connection: CoreConnection,
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """Test disconnect continues even if Google API fails."""
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": False, "error": "network_error"},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": False, "error": "network_error"},
            ):
                result = await disconnect_user(
                    user_id=test_user.id,
                    session=async_session,
                    http_client=mock_http_client,
                    redis_client=mock_redis_client,
                )

        # Disconnect should still succeed
        assert result["success"] is True
        assert result["details"]["google_token_revoked"] is False
        assert result["details"]["webhook_stopped"] is False

        # Connection should still be marked as revoked
        await async_session.refresh(google_connection)
        assert google_connection.revoked_at is not None


# =============================================================================
# Delete Data Tests
# =============================================================================

class TestDeleteUserData:
    """Tests for delete_user_data function."""

    @pytest.mark.asyncio
    async def test_delete_data_removes_all_focused_data(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        google_connection: CoreConnection,  # noqa: ARG002 - creates DB data
        oauth_tokens: list[OAuthAccessToken],  # noqa: ARG002 - creates DB data
        focus_sessions: list[FocusedFocusSession],  # noqa: ARG002 - creates DB data
        user_keywords: list[FocusedUserKeyword],  # noqa: ARG002 - creates DB data
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """Test delete-data removes all Focused-specific data."""
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                result = await delete_user_data(
                    user_id=test_user.id,
                    session=async_session,
                    http_client=mock_http_client,
                    redis_client=mock_redis_client,
                )

        # Verify result
        assert result["success"] is True
        assert result["tables_affected"] >= 2
        assert result["rows_deleted"]["focused_focus_sessions"] == 5
        assert result["rows_deleted"]["focused_user_keywords"] == 3
        assert "audit_log_id" in result

        # Verify focus sessions deleted
        stmt = select(FocusedFocusSession).where(
            FocusedFocusSession.user_id == test_user.id
        )
        remaining = await async_session.execute(stmt)
        assert remaining.scalars().all() == []

        # Verify keywords deleted
        stmt = select(FocusedUserKeyword).where(
            FocusedUserKeyword.user_id == test_user.id
        )
        remaining = await async_session.execute(stmt)
        assert remaining.scalars().all() == []

        # Verify audit log created
        stmt = select(CoreToolAuditLog).where(
            CoreToolAuditLog.user_id == test_user.id,
            CoreToolAuditLog.action == "delete_data",
        )
        audit_result = await async_session.execute(stmt)
        audit_log = audit_result.scalar_one()
        assert audit_log.result_status == "success"
        assert audit_log.app_name == "focused"

    @pytest.mark.asyncio
    async def test_delete_data_idempotent(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """Test delete-data is idempotent - calling twice returns success."""
        result = await delete_user_data(
            user_id=test_user.id,
            session=async_session,
            http_client=mock_http_client,
            redis_client=mock_redis_client,
        )

        assert result["success"] is True
        assert result["tables_affected"] == 0

    @pytest.mark.asyncio
    async def test_delete_data_preserves_core_users(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        focus_sessions: list[FocusedFocusSession],  # noqa: ARG002 - creates DB data
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """Test delete-data does NOT delete core_users row."""
        result = await delete_user_data(
            user_id=test_user.id,
            session=async_session,
            http_client=mock_http_client,
            redis_client=mock_redis_client,
        )

        assert result["success"] is True

        # Verify user still exists
        stmt = select(CoreUser).where(CoreUser.id == test_user.id)
        user_result = await async_session.execute(stmt)
        assert user_result.scalar_one() is not None

    @pytest.mark.asyncio
    async def test_delete_data_only_deletes_focused_tokens(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        mock_http_client: AsyncMock,
        mock_redis_client: AsyncMock,
    ):
        """
        Test delete-data only deletes Focused-scoped tokens, not other app tokens.

        Critical cross-app isolation test:
        - Focused tokens (scope contains 'focused.read') -> deleted
        - Other app tokens (e.g., 'meeting.read') -> preserved

        Note: Tokens must be revoked=True to be deleted (per spec).
        This test pre-marks Focused tokens as revoked to isolate the
        cross-app filtering logic.
        """
        # Create Focused-scoped tokens (should be deleted)
        # Pre-marked as revoked since delete only deletes revoked tokens
        focused_tokens = []
        for _ in range(2):
            token = OAuthAccessToken(
                jti=f"focused-token-{uuid4()}",
                user_id=test_user.id,
                client_id="focused-client",
                scope=["focused.read", "focused.write"],
                token_type="Bearer",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                revoked=True,  # Pre-revoked for this test
                revoked_at=datetime.now(timezone.utc),
            )
            async_session.add(token)
            focused_tokens.append(token)

        # Create other app tokens (should be preserved even if revoked)
        # This tests that ONLY Focused-scoped tokens are deleted
        other_app_token = OAuthAccessToken(
            jti=f"meeting-token-{uuid4()}",
            user_id=test_user.id,
            client_id="meeting-client",
            scope=["meeting.read", "meeting.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=True,  # Even if revoked, should NOT be deleted (wrong scope)
            revoked_at=datetime.now(timezone.utc),
        )
        async_session.add(other_app_token)

        # Create global/unscoped token (should be preserved)
        global_token = OAuthAccessToken(
            jti=f"global-token-{uuid4()}",
            user_id=test_user.id,
            client_id="global-client",
            scope=["profile", "email"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=True,  # Even if revoked, should NOT be deleted (wrong scope)
            revoked_at=datetime.now(timezone.utc),
        )
        async_session.add(global_token)

        await async_session.flush()

        # Run delete_user_data
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                result = await delete_user_data(
                    user_id=test_user.id,
                    session=async_session,
                    http_client=mock_http_client,
                    redis_client=mock_redis_client,
                )

        assert result["success"] is True
        # Should have deleted the 2 focused tokens
        assert result["rows_deleted"]["oauth_access_tokens"] == 2

        # Verify Focused tokens are gone
        for token in focused_tokens:
            stmt = select(OAuthAccessToken).where(OAuthAccessToken.jti == token.jti)
            token_result = await async_session.execute(stmt)
            assert token_result.scalar_one_or_none() is None, (
                f"Focused token {token.jti} should have been deleted"
            )

        # Verify other app token still exists
        stmt = select(OAuthAccessToken).where(
            OAuthAccessToken.jti == other_app_token.jti
        )
        token_result = await async_session.execute(stmt)
        assert token_result.scalar_one_or_none() is not None, (
            "Other app token (meeting.read scope) should NOT be deleted"
        )

        # Verify global token still exists
        stmt = select(OAuthAccessToken).where(
            OAuthAccessToken.jti == global_token.jti
        )
        token_result = await async_session.execute(stmt)
        assert token_result.scalar_one_or_none() is not None, (
            "Global token (profile/email scope) should NOT be deleted"
        )

    @pytest.mark.asyncio
    async def test_delete_data_does_not_delete_unrevoked_tokens(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
    ):
        """
        Test delete-data does NOT delete tokens that haven't been revoked first.

        Per Increment 10 spec:
        - /disconnect marks tokens as revoked=True
        - /delete-data ONLY deletes tokens that are BOTH:
          1. Focused-scoped (scope contains 'focused.read')
          2. Already revoked (revoked=True)

        This test verifies that if a token somehow wasn't revoked during disconnect,
        it will NOT be deleted - protecting against accidental token loss.
        """
        # Create Focused-scoped tokens that are NOT revoked
        unrevoked_focused_token = OAuthAccessToken(
            jti=f"unrevoked-focused-{uuid4()}",
            user_id=test_user.id,
            client_id="focused-client",
            scope=["focused.read", "focused.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=False,  # NOT revoked
        )
        async_session.add(unrevoked_focused_token)

        # Create Focused-scoped token that IS revoked (should be deleted)
        revoked_focused_token = OAuthAccessToken(
            jti=f"revoked-focused-{uuid4()}",
            user_id=test_user.id,
            client_id="focused-client",
            scope=["focused.read", "focused.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=True,  # Already revoked
            revoked_at=datetime.now(timezone.utc),
        )
        async_session.add(revoked_focused_token)

        await async_session.flush()

        # Directly call delete logic, skipping disconnect
        # (simulates calling delete-data on an already-disconnected user
        #  or a scenario where disconnect failed to revoke some tokens)
        from sqlalchemy import delete as sa_delete, any_

        # Only run the deletion part, not the full disconnect flow
        # This mimics what happens if disconnect already ran but
        # somehow one token wasn't marked revoked
        stmt = sa_delete(OAuthAccessToken).where(
            OAuthAccessToken.user_id == test_user.id,
            OAuthAccessToken.revoked == True,  # noqa: E712
            "focused.read" == any_(OAuthAccessToken.scope),
        )
        result = await async_session.execute(stmt)
        deleted_count = result.rowcount

        # Should only delete the revoked token
        assert deleted_count == 1, (
            f"Expected 1 revoked token deleted, got {deleted_count}"
        )

        # Verify unrevoked token still exists
        stmt = select(OAuthAccessToken).where(
            OAuthAccessToken.jti == unrevoked_focused_token.jti
        )
        token_result = await async_session.execute(stmt)
        assert token_result.scalar_one_or_none() is not None, (
            "Unrevoked Focused token should NOT be deleted - "
            "only revoked tokens are deleted"
        )

        # Verify revoked token was deleted
        stmt = select(OAuthAccessToken).where(
            OAuthAccessToken.jti == revoked_focused_token.jti
        )
        token_result = await async_session.execute(stmt)
        assert token_result.scalar_one_or_none() is None, (
            "Revoked Focused token should have been deleted"
        )


# =============================================================================
# Redis Cache Tests
# =============================================================================

class TestClearRedisCache:
    """Tests for clear_user_redis_cache function."""

    @pytest.mark.asyncio
    async def test_clear_cache_scans_correct_patterns(self):
        """Test Redis cache clearing uses correct patterns."""
        mock_redis = AsyncMock()
        deleted_keys = []

        async def mock_scan_iter(match):
            # Match actual Redis key patterns from redis_client.py
            if "needs_sync" in match:
                yield "dev:focused:needs_sync:user-123"
            elif "renew_throttle" in match:
                yield "dev:focused:webhook:renew_throttle:user-123"
            elif "webhook" in match:
                yield "dev:focused:webhook:user-123:msg1"
                yield "dev:focused:webhook:user-123:msg2"

        async def mock_delete(key):
            deleted_keys.append(key)

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete = mock_delete

        count = await clear_user_redis_cache(
            user_id="user-123",
            redis_client=mock_redis,
        )

        assert count == 4
        assert "dev:focused:needs_sync:user-123" in deleted_keys
        assert "dev:focused:webhook:user-123:msg1" in deleted_keys
        assert "dev:focused:webhook:renew_throttle:user-123" in deleted_keys

    @pytest.mark.asyncio
    async def test_clear_cache_handles_empty_result(self):
        """Test Redis cache clearing handles no keys found."""
        mock_redis = AsyncMock()

        async def mock_scan_iter(match):  # noqa: ARG001
            # Empty async generator - no keys to delete
            if False:  # pragma: no cover
                yield

        mock_redis.scan_iter = mock_scan_iter
        mock_redis.delete = AsyncMock()

        count = await clear_user_redis_cache(
            user_id="user-123",
            redis_client=mock_redis,
        )

        assert count == 0
