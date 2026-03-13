"""
Unit tests for Priority Guardian offboarding router.

Tests the disconnect endpoint logic:
- PG OAuth tokens are NOT revoked (Inc 63 fix)
- Google connection is still marked as revoked
- Idempotent behavior on double disconnect
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException


class TestDisconnectDoesNotRevokePGTokens:
    """Tests that disconnect does NOT revoke PG OAuth tokens (Inc 63 fix)."""

    @pytest.mark.asyncio
    async def test_disconnect_does_not_revoke_pg_tokens(self):
        """Disconnect should NOT call UPDATE on oauth_access_tokens.

        The fix removes the PG token revocation block entirely.
        Only Google token revocation at Google + core_connections update should happen.
        """
        from backend.apps.priority_guardian.routers.offboarding_router import disconnect

        user_id = uuid4()

        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id

        # Mock connection (not yet revoked)
        mock_connection = MagicMock()
        mock_connection.revoked_at = None
        mock_connection.encrypted_refresh_token = "encrypted_token"

        # Mock session
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_user)

        # Connection query result
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection
        mock_session.execute = AsyncMock(return_value=conn_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        # Mock request
        mock_request = MagicMock()
        mock_request.app.state.http_client = MagicMock()

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.decrypt_token",
            return_value="decrypted_token"
        ), patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True}
        ):
            result = await disconnect(
                request=mock_request,
                x_user_id=str(user_id),
                session=mock_session,
            )

        # Verify no pg_tokens_revoked in response
        assert "pg_tokens_revoked" not in result["details"]

        # Verify no execute call involved oauth_access_tokens
        for call in mock_session.execute.call_args_list:
            assert "oauth_access_tokens" not in str(call)

    @pytest.mark.asyncio
    async def test_disconnect_keeps_session_valid(self):
        """After disconnect, active access token remains unrevoked.

        The session should remain valid for subsequent MCP tool calls.
        """
        from backend.apps.priority_guardian.routers.offboarding_router import disconnect

        user_id = uuid4()

        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id

        # Mock connection
        mock_connection = MagicMock()
        mock_connection.revoked_at = None
        mock_connection.encrypted_refresh_token = "encrypted_token"

        # Mock session
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_user)

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection
        mock_session.execute = AsyncMock(return_value=conn_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        # Mock request
        mock_request = MagicMock()
        mock_request.app.state.http_client = MagicMock()

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.decrypt_token",
            return_value="decrypted_token"
        ), patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True}
        ):
            result = await disconnect(
                request=mock_request,
                x_user_id=str(user_id),
                session=mock_session,
            )

        # Verify success without token revocation
        assert result["status"] == "disconnected"
        assert result["already_disconnected"] is False
        # No oauth_access_tokens UPDATE means session remains valid


class TestDisconnectRevokesGoogleConnection:
    """Tests that disconnect still revokes Google connection (regression guard)."""

    @pytest.mark.asyncio
    async def test_disconnect_revokes_google_connection(self):
        """Disconnect should still mark core_connections.revoked_at."""
        from backend.apps.priority_guardian.routers.offboarding_router import disconnect

        user_id = uuid4()

        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id

        # Mock connection
        mock_connection = MagicMock()
        mock_connection.revoked_at = None
        mock_connection.encrypted_refresh_token = "encrypted_token"

        # Mock session
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_user)

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection
        mock_session.execute = AsyncMock(return_value=conn_result)
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()

        # Mock request
        mock_request = MagicMock()
        mock_request.app.state.http_client = MagicMock()

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.decrypt_token",
            return_value="decrypted_token"
        ), patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True}
        ):
            result = await disconnect(
                request=mock_request,
                x_user_id=str(user_id),
                session=mock_session,
            )

        # Verify connection was marked as revoked
        assert mock_connection.revoked_at is not None
        assert result["details"]["google_connection_revoked"] is True

        # Verify flush and commit were called
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_no_connection_skips_revocation(self):
        """Disconnect with no Google connection should skip revocation."""
        from backend.apps.priority_guardian.routers.offboarding_router import disconnect

        user_id = uuid4()

        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id

        # Mock session - no connection found
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_user)

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=conn_result)
        mock_session.commit = AsyncMock()

        # Mock request
        mock_request = MagicMock()

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
        ) as mock_revoke:
            result = await disconnect(
                request=mock_request,
                x_user_id=str(user_id),
                session=mock_session,
            )

        # Verify revoke was not called (no connection)
        mock_revoke.assert_not_called()

        # Verify response
        assert result["status"] == "disconnected"
        assert result["details"]["google_connection_revoked"] is False


class TestDisconnectIdempotent:
    """Tests that disconnect is idempotent."""

    @pytest.mark.asyncio
    async def test_disconnect_already_disconnected_idempotent(self):
        """Second disconnect call returns 200 with already_disconnected: True."""
        from backend.apps.priority_guardian.routers.offboarding_router import disconnect

        user_id = uuid4()
        revoked_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        # Mock user
        mock_user = MagicMock()
        mock_user.id = user_id

        # Mock connection (already revoked)
        mock_connection = MagicMock()
        mock_connection.revoked_at = revoked_time

        # Mock session
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_user)

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection
        mock_session.execute = AsyncMock(return_value=conn_result)
        mock_session.commit = AsyncMock()

        # Mock request
        mock_request = MagicMock()

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
        ) as mock_revoke:
            result = await disconnect(
                request=mock_request,
                x_user_id=str(user_id),
                session=mock_session,
            )

        # Verify revoke was not called (already disconnected)
        mock_revoke.assert_not_called()

        # Verify idempotent response
        assert result["status"] == "disconnected"
        assert result["already_disconnected"] is True
        assert result["revoked_at"] == revoked_time.isoformat()


class TestDisconnectErrorHandling:
    """Tests for disconnect error handling."""

    @pytest.mark.asyncio
    async def test_disconnect_user_not_found_returns_404(self):
        """Disconnect returns 404 when user does not exist."""
        from backend.apps.priority_guardian.routers.offboarding_router import disconnect

        user_id = uuid4()

        # Mock session - user not found
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        # Mock request
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await disconnect(
                request=mock_request,
                x_user_id=str(user_id),
                session=mock_session,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "User not found"

    @pytest.mark.asyncio
    async def test_disconnect_invalid_user_id_returns_400(self):
        """Disconnect returns 400 for invalid UUID format."""
        from backend.apps.priority_guardian.routers.offboarding_router import disconnect

        # Mock session
        mock_session = AsyncMock()

        # Mock request
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await disconnect(
                request=mock_request,
                x_user_id="not-a-valid-uuid",
                session=mock_session,
            )

        assert exc_info.value.status_code == 400
        assert "Invalid user ID" in exc_info.value.detail
