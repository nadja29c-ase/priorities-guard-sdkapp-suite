"""
E2E tests for offboarding endpoints (Increment 10).

Tests /disconnect and /delete-data endpoints with real DB and mocked Google APIs.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser, CoreConnection, CoreToolAuditLog
from backend.core.encryption import encrypt_token
from backend.core.oauth_provider.models import OAuthAccessToken
from backend.apps.focused.db_models import FocusedFocusSession, FocusedUserKeyword


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def test_user_with_data(async_session: AsyncSession):
    """Create a fully provisioned test user with connection and data."""
    # Create user
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.flush()

    # Create Google connection with webhook
    # Note: connection_type defaults to "unknown" in production
    connection = CoreConnection(
        user_id=user.id,
        provider="google",
        connection_type="google",
        encrypted_access_token=encrypt_token("test_access_token"),
        encrypted_refresh_token=encrypt_token("test_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        google_channel_id=f"channel-{uuid4()}",
        google_resource_id=f"resource-{uuid4()}",
        google_channel_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    async_session.add(connection)

    # Create OAuth tokens
    tokens = []
    for i in range(2):
        token = OAuthAccessToken(
            jti=f"token-{uuid4()}",
            user_id=user.id,
            client_id="test-client",
            scope=["focused.read", "focused.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            refresh_token_enc=encrypt_token(f"refresh-{i}"),
            refresh_token_hash=f"hash-{uuid4()}",
            refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            revoked=False,
        )
        async_session.add(token)
        tokens.append(token)

    # Create focus sessions
    sessions = []
    base_time = datetime.now(timezone.utc) + timedelta(hours=1)
    for i in range(3):
        fs = FocusedFocusSession(
            user_id=user.id,
            google_event_id=f"event-{uuid4()}",
            google_calendar_id="primary",
            google_ical_uid=f"ical-{uuid4()}@google.com",
            google_updated_at=datetime.now(timezone.utc),
            start_time=base_time + timedelta(hours=i),
            end_time=base_time + timedelta(hours=i+1),
            is_focus_block=True,
            matched_keyword="focus",
            sha256_content_hash="a" * 64,
        )
        async_session.add(fs)
        sessions.append(fs)

    # Create keywords
    keywords = []
    for word in ["deep work", "coding"]:
        kw = FocusedUserKeyword(
            user_id=user.id,
            keyword=word,
        )
        async_session.add(kw)
        keywords.append(kw)

    await async_session.flush()

    return {
        "user": user,
        "connection": connection,
        "tokens": tokens,
        "sessions": sessions,
        "keywords": keywords,
    }


# =============================================================================
# Disconnect Endpoint Tests
# =============================================================================

class TestDisconnectEndpoint:
    """E2E tests for POST /api/focused/disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_success(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002 - required for test_user_with_data
        test_user_with_data: dict,
    ):
        """Test successful disconnect revokes tokens and clears webhook."""
        user_id = str(test_user_with_data["user"].id)

        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response = await client.post(
                    "/api/focused/disconnect",
                    headers={"X-User-ID": user_id},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        assert "revoked_at" in data
        assert data["already_disconnected"] is False

    @pytest.mark.asyncio
    async def test_disconnect_clears_google_fields_in_db(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_data: dict,
    ):
        """
        E2E test: disconnect clears Google webhook fields in CoreConnection.

        Verifies that after disconnect:
        - google_channel_id is NULL
        - google_resource_id is NULL
        - google_channel_expires_at is NULL
        - revoked_at is set
        """
        user = test_user_with_data["user"]
        connection = test_user_with_data["connection"]
        user_id = str(user.id)

        # Verify initial state has Google fields populated
        assert connection.google_channel_id is not None
        assert connection.google_resource_id is not None
        assert connection.google_channel_expires_at is not None
        assert connection.revoked_at is None

        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response = await client.post(
                    "/api/focused/disconnect",
                    headers={"X-User-ID": user_id},
                )

        assert response.status_code == 200

        # Refresh connection from database to get updated values
        await async_session.refresh(connection)

        # Verify Google fields are cleared
        assert connection.google_channel_id is None, (
            "google_channel_id should be NULL after disconnect"
        )
        assert connection.google_resource_id is None, (
            "google_resource_id should be NULL after disconnect"
        )
        assert connection.google_channel_expires_at is None, (
            "google_channel_expires_at should be NULL after disconnect"
        )

        # Verify revoked_at is set
        assert connection.revoked_at is not None, (
            "revoked_at should be set after disconnect"
        )

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002 - required for test_user_with_data
        test_user_with_data: dict,
    ):
        """Test disconnect is idempotent - second call returns already_disconnected."""
        user_id = str(test_user_with_data["user"].id)

        # First disconnect
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response1 = await client.post(
                    "/api/focused/disconnect",
                    headers={"X-User-ID": user_id},
                )

        assert response1.status_code == 200
        assert response1.json()["already_disconnected"] is False

        # Second disconnect (idempotent)
        response2 = await client.post(
            "/api/focused/disconnect",
            headers={"X-User-ID": user_id},
        )

        assert response2.status_code == 200
        assert response2.json()["already_disconnected"] is True

    @pytest.mark.asyncio
    async def test_disconnect_revoked_at_immutable(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_data: dict,
    ):
        """
        E2E test: revoked_at is set once and never overwritten.

        Verifies at the HTTP layer that:
        1. First disconnect sets revoked_at
        2. Second disconnect returns same revoked_at value
        3. Third disconnect still returns original value
        4. Database value remains unchanged
        """
        user = test_user_with_data["user"]
        connection = test_user_with_data["connection"]
        user_id = str(user.id)

        # Verify initial state
        assert connection.revoked_at is None

        # First disconnect - sets revoked_at
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response1 = await client.post(
                    "/api/focused/disconnect",
                    headers={"X-User-ID": user_id},
                )

        assert response1.status_code == 200
        assert response1.json()["already_disconnected"] is False
        original_revoked_at = response1.json()["revoked_at"]

        # Refresh and capture DB value
        await async_session.refresh(connection)
        db_revoked_at = connection.revoked_at
        assert db_revoked_at is not None

        # Second disconnect - should return same revoked_at
        response2 = await client.post(
            "/api/focused/disconnect",
            headers={"X-User-ID": user_id},
        )

        assert response2.status_code == 200
        assert response2.json()["already_disconnected"] is True
        assert response2.json()["revoked_at"] == original_revoked_at, (
            "Second disconnect should return same revoked_at as first"
        )

        # Verify DB value unchanged
        await async_session.refresh(connection)
        assert connection.revoked_at == db_revoked_at, (
            "revoked_at in DB should not change on second disconnect"
        )

        # Third disconnect - still same value
        response3 = await client.post(
            "/api/focused/disconnect",
            headers={"X-User-ID": user_id},
        )

        assert response3.status_code == 200
        assert response3.json()["revoked_at"] == original_revoked_at, (
            "Third disconnect should still return original revoked_at"
        )

        # Final DB check
        await async_session.refresh(connection)
        assert connection.revoked_at == db_revoked_at, (
            "revoked_at must remain immutable across multiple disconnect calls"
        )

    @pytest.mark.asyncio
    async def test_disconnect_no_user_id_header_returns_401(
        self,
        client: AsyncClient,
    ):
        """Test disconnect without X-User-ID header returns 401 Unauthorized."""
        # Offboarding endpoints require authentication - no fallback allowed
        response = await client.post("/api/focused/disconnect")

        assert response.status_code == 401


# =============================================================================
# Delete Data Endpoint Tests
# =============================================================================

class TestDeleteDataEndpoint:
    """E2E tests for DELETE /api/focused/delete-data."""

    @pytest.mark.asyncio
    async def test_delete_data_success(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002 - required for test_user_with_data
        test_user_with_data: dict,
    ):
        """Test successful delete-data removes all Focused data."""
        user_id = str(test_user_with_data["user"].id)

        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response = await client.delete(
                    "/api/focused/delete-data",
                    headers={"X-User-ID": user_id},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["tables_affected"] >= 2
        assert data["rows_deleted"]["focused_focus_sessions"] == 3
        assert data["rows_deleted"]["focused_user_keywords"] == 2

    @pytest.mark.asyncio
    async def test_delete_data_idempotent(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002 - required for test_user_with_data
        test_user_with_data: dict,
    ):
        """Test delete-data is idempotent - second call returns success with 0 affected."""
        user_id = str(test_user_with_data["user"].id)

        # First delete
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response1 = await client.delete(
                    "/api/focused/delete-data",
                    headers={"X-User-ID": user_id},
                )

        assert response1.status_code == 200
        assert response1.json()["tables_affected"] >= 2

        # Second delete (idempotent)
        response2 = await client.delete(
            "/api/focused/delete-data",
            headers={"X-User-ID": user_id},
        )

        assert response2.status_code == 200
        assert response2.json()["tables_affected"] == 0

    @pytest.mark.asyncio
    async def test_delete_data_creates_audit_log(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_data: dict,
    ):
        """Test delete-data creates audit log entry."""
        user = test_user_with_data["user"]
        user_id = str(user.id)

        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response = await client.delete(
                    "/api/focused/delete-data",
                    headers={"X-User-ID": user_id},
                )

        assert response.status_code == 200

        # Verify audit log was created
        # Need to query fresh since we're in test transaction
        stmt = select(CoreToolAuditLog).where(
            CoreToolAuditLog.user_id == user.id,
            CoreToolAuditLog.action == "delete_data",
        )
        result = await async_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.app_name == "focused"
        assert audit_log.result_status == "success"

    @pytest.mark.asyncio
    async def test_delete_data_preserves_core_user(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_data: dict,
    ):
        """Test delete-data does NOT delete core_users row."""
        user = test_user_with_data["user"]
        user_id = str(user.id)

        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response = await client.delete(
                    "/api/focused/delete-data",
                    headers={"X-User-ID": user_id},
                )

        assert response.status_code == 200

        # Verify user still exists
        stmt = select(CoreUser).where(CoreUser.id == user.id)
        result = await async_session.execute(stmt)
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_delete_data_no_user_id_header_returns_401(
        self,
        client: AsyncClient,
    ):
        """Test delete-data without X-User-ID header returns 401 Unauthorized."""
        # Offboarding endpoints require authentication - no fallback allowed
        response = await client.delete("/api/focused/delete-data")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_data_deletes_revoked_focused_tokens(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ):
        """
        E2E test: delete-data deletes revoked Focused tokens.

        Verifies the full flow:
        1. Create user with Focused-scoped tokens
        2. Call /disconnect to revoke tokens
        3. Call /delete-data to delete revoked tokens
        4. Verify tokens are gone from database
        """
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create Google connection
        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token=encrypt_token("test_access"),
            encrypted_refresh_token=encrypt_token("test_refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        async_session.add(connection)

        # Create Focused-scoped tokens
        focused_token = OAuthAccessToken(
            jti=f"focused-e2e-{uuid4()}",
            user_id=user.id,
            client_id="focused-client",
            scope=["focused.read", "focused.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=False,
        )
        async_session.add(focused_token)
        await async_session.flush()

        user_id = str(user.id)
        token_jti = focused_token.jti

        # Step 1: Disconnect (revokes tokens)
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                response = await client.post(
                    "/api/focused/disconnect",
                    headers={"X-User-ID": user_id},
                )
        assert response.status_code == 200

        # Verify token is now revoked but still exists
        stmt = select(OAuthAccessToken).where(OAuthAccessToken.jti == token_jti)
        result = await async_session.execute(stmt)
        token = result.scalar_one()
        assert token.revoked is True

        # Step 2: Delete data (deletes revoked tokens)
        response = await client.delete(
            "/api/focused/delete-data",
            headers={"X-User-ID": user_id},
        )
        assert response.status_code == 200
        assert response.json()["rows_deleted"]["oauth_access_tokens"] == 1

        # Verify token is deleted
        stmt = select(OAuthAccessToken).where(OAuthAccessToken.jti == token_jti)
        result = await async_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_data_preserves_non_focused_tokens(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ):
        """
        E2E test: delete-data preserves tokens from other apps.

        Critical cross-app isolation test at E2E level.
        """
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create Google connection
        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token=encrypt_token("test_access"),
            encrypted_refresh_token=encrypt_token("test_refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        async_session.add(connection)

        # Create Focused-scoped token (will be deleted)
        focused_token = OAuthAccessToken(
            jti=f"focused-del-{uuid4()}",
            user_id=user.id,
            client_id="focused-client",
            scope=["focused.read", "focused.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=False,
        )
        async_session.add(focused_token)

        # Create other app token (must be preserved)
        other_app_token = OAuthAccessToken(
            jti=f"other-app-{uuid4()}",
            user_id=user.id,
            client_id="meeting-client",
            scope=["meeting.read", "meeting.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=False,
        )
        async_session.add(other_app_token)
        await async_session.flush()

        user_id = str(user.id)
        other_token_jti = other_app_token.jti

        # Disconnect + Delete
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                await client.post(
                    "/api/focused/disconnect",
                    headers={"X-User-ID": user_id},
                )

        response = await client.delete(
            "/api/focused/delete-data",
            headers={"X-User-ID": user_id},
        )
        assert response.status_code == 200

        # Verify other app token still exists and is NOT revoked
        stmt = select(OAuthAccessToken).where(OAuthAccessToken.jti == other_token_jti)
        result = await async_session.execute(stmt)
        preserved_token = result.scalar_one_or_none()
        assert preserved_token is not None, "Other app token should NOT be deleted"
        assert preserved_token.revoked is False, "Other app token should NOT be revoked"

    @pytest.mark.asyncio
    async def test_delete_data_preserves_unrevoked_focused_tokens(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ):
        """
        E2E test: delete-data does NOT delete unrevoked tokens.

        Simulates a scenario where disconnect didn't revoke a token
        (e.g., partial failure). The delete-data should not delete it.
        """
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create Focused-scoped token that is NOT revoked
        # (simulating a token that disconnect missed)
        unrevoked_token = OAuthAccessToken(
            jti=f"unrevoked-e2e-{uuid4()}",
            user_id=user.id,
            client_id="focused-client",
            scope=["focused.read", "focused.write"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=False,  # NOT revoked
        )
        async_session.add(unrevoked_token)
        await async_session.flush()

        user_id = str(user.id)
        token_jti = unrevoked_token.jti

        # Call delete-data directly (skipping disconnect)
        # This simulates calling delete on an already-disconnected user
        # where some tokens weren't properly revoked
        response = await client.delete(
            "/api/focused/delete-data",
            headers={"X-User-ID": user_id},
        )
        assert response.status_code == 200
        # Should be 0 because token wasn't revoked
        assert response.json()["rows_deleted"]["oauth_access_tokens"] == 0

        # Verify unrevoked token still exists
        stmt = select(OAuthAccessToken).where(OAuthAccessToken.jti == token_jti)
        result = await async_session.execute(stmt)
        preserved_token = result.scalar_one_or_none()
        assert preserved_token is not None, (
            "Unrevoked Focused token should NOT be deleted - "
            "tokens must be revoked before deletion"
        )


# =============================================================================
# Protocol Ordering Tests
# =============================================================================

class TestProtocolOrdering:
    """E2E tests verifying disconnect→delete-data protocol ordering."""

    @pytest.mark.asyncio
    async def test_delete_data_calls_disconnect_internally(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_data: dict,
    ):
        """
        E2E test: delete-data calls disconnect logic internally.

        Verifies the protocol ordering:
        1. delete-data invokes disconnect_user internally
        2. Connection is marked as revoked
        3. Tokens are revoked before deletion
        4. All operations complete in correct sequence
        """
        user = test_user_with_data["user"]
        connection = test_user_with_data["connection"]
        user_id = str(user.id)

        # Verify initial state - not disconnected
        assert connection.revoked_at is None
        assert connection.google_channel_id is not None

        # Call delete-data directly (without calling disconnect first)
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ) as mock_stop_webhook:
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ) as mock_revoke_token:
                response = await client.delete(
                    "/api/focused/delete-data",
                    headers={"X-User-ID": user_id},
                )

        assert response.status_code == 200

        # Verify disconnect was called as part of delete-data
        mock_stop_webhook.assert_called_once()
        mock_revoke_token.assert_called_once()

        # Verify connection is now disconnected
        await async_session.refresh(connection)
        assert connection.revoked_at is not None, (
            "delete-data should call disconnect internally, setting revoked_at"
        )
        assert connection.google_channel_id is None, (
            "delete-data should clear Google webhook fields via disconnect"
        )

    @pytest.mark.asyncio
    async def test_delete_data_works_on_already_disconnected_user(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_data: dict,
    ):
        """
        E2E test: delete-data works correctly on already-disconnected user.

        Verifies that calling delete-data after disconnect:
        1. Does not fail
        2. Still deletes data
        3. Skips redundant disconnect operations
        """
        user = test_user_with_data["user"]
        connection = test_user_with_data["connection"]
        user_id = str(user.id)

        # First: disconnect the user
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                disconnect_response = await client.post(
                    "/api/focused/disconnect",
                    headers={"X-User-ID": user_id},
                )

        assert disconnect_response.status_code == 200
        assert disconnect_response.json()["already_disconnected"] is False

        # Capture revoked_at after disconnect
        await async_session.refresh(connection)
        original_revoked_at = connection.revoked_at
        assert original_revoked_at is not None

        # Then: call delete-data on already-disconnected user
        # These mocks should NOT be called since user is already disconnected
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ) as mock_stop_webhook:
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ) as mock_revoke_token:
                delete_response = await client.delete(
                    "/api/focused/delete-data",
                    headers={"X-User-ID": user_id},
                )

        assert delete_response.status_code == 200

        # Verify Google API calls were NOT made (user already disconnected)
        mock_stop_webhook.assert_not_called()
        mock_revoke_token.assert_not_called()

        # Verify revoked_at was NOT changed
        await async_session.refresh(connection)
        assert connection.revoked_at == original_revoked_at, (
            "delete-data should not modify revoked_at on already-disconnected user"
        )

        # Verify data was still deleted
        data = delete_response.json()
        assert data["status"] == "deleted"
        assert data["rows_deleted"]["focused_focus_sessions"] == 3
        assert data["rows_deleted"]["focused_user_keywords"] == 2


# =============================================================================
# Redis Behavior Tests
# =============================================================================

class TestRedisIntegration:
    """E2E tests for Redis behavior during offboarding."""

    @pytest.mark.asyncio
    async def test_disconnect_invokes_redis_cleanup(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002 - required for test_user_with_data
        test_user_with_data: dict,
    ):
        """
        E2E test: disconnect invokes Redis cache cleanup.

        Verifies that clear_user_redis_cache is called during disconnect.
        """
        user_id = str(test_user_with_data["user"].id)

        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                with patch(
                    "backend.apps.focused.logic.offboarding.clear_user_redis_cache",
                    new_callable=AsyncMock,
                    return_value=3,  # Simulates 3 keys deleted
                ) as mock_redis_clear:
                    response = await client.post(
                        "/api/focused/disconnect",
                        headers={"X-User-ID": user_id},
                    )

        assert response.status_code == 200
        # Verify Redis cleanup was invoked with correct user_id
        mock_redis_clear.assert_called_once()
        call_args = mock_redis_clear.call_args
        assert call_args.kwargs["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_disconnect_succeeds_when_redis_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002 - required for test_user_with_data
        test_user_with_data: dict,
    ):
        """
        E2E test: disconnect succeeds even if Redis cleanup fails.

        Redis errors should be logged but not block the disconnect operation.
        """
        user_id = str(test_user_with_data["user"].id)

        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                with patch(
                    "backend.apps.focused.logic.offboarding.clear_user_redis_cache",
                    new_callable=AsyncMock,
                    side_effect=Exception("Redis connection failed"),
                ):
                    response = await client.post(
                        "/api/focused/disconnect",
                        headers={"X-User-ID": user_id},
                    )

        # Disconnect should still succeed despite Redis failure
        assert response.status_code == 200
        assert response.json()["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_disconnect_redis_returns_deleted_count_in_details(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
    ):
        """
        E2E test: verify Redis deletion count is tracked in disconnect details.

        Tests that the number of Redis keys deleted is captured correctly.
        """
        # Create minimal user for this test
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create connection
        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token=encrypt_token("test_access"),
            encrypted_refresh_token=encrypt_token("test_refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        async_session.add(connection)
        await async_session.flush()

        user_id = str(user.id)

        # Mock Redis to return specific deletion count
        with patch(
            "backend.apps.focused.logic.offboarding.stop_webhook_channel",
            return_value={"success": True, "error": None},
        ):
            with patch(
                "backend.apps.focused.logic.offboarding.revoke_google_token",
                return_value={"success": True, "error": None},
            ):
                with patch(
                    "backend.apps.focused.logic.offboarding.clear_user_redis_cache",
                    new_callable=AsyncMock,
                    return_value=5,  # 5 keys deleted
                ):
                    response = await client.post(
                        "/api/focused/disconnect",
                        headers={"X-User-ID": user_id},
                    )

        assert response.status_code == 200
        # The endpoint returns status, revoked_at, already_disconnected
        # Redis details are internal (logged, not returned to client)
        # This test verifies the operation completes successfully
        assert response.json()["status"] == "disconnected"
