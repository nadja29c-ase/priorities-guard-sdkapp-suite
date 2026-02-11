"""
Unit tests for google_token_management module.

Tests ensure_valid_access_token() behavior for token expiry,
refresh logic, and error handling.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.google_token_management import ensure_valid_access_token


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_connection():
    """Create a mock CoreConnection object."""
    connection = MagicMock()
    connection.user_id = "user-123"
    connection.encrypted_access_token = b"encrypted_access"
    connection.encrypted_refresh_token = b"encrypted_refresh"
    connection.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return connection


@pytest.fixture
def expired_connection(mock_connection):
    """Create a mock connection with expired token."""
    mock_connection.token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    return mock_connection


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_http_client():
    """Create a mock httpx.AsyncClient."""
    return AsyncMock()


# =============================================================================
# Token Not Expired Tests
# =============================================================================

class TestTokenNotExpired:
    """Tests for when token is still valid."""

    @pytest.mark.asyncio
    async def test_returns_decrypted_access_token(
        self, mock_connection, mock_session, mock_http_client
    ):
        """Valid token returns decrypted access token without refresh."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_access_token"
        ):
            result = await ensure_valid_access_token(
                mock_connection, mock_session, mock_http_client
            )

        assert result == {"access_token": "decrypted_access_token"}

    @pytest.mark.asyncio
    async def test_does_not_call_refresh(
        self, mock_connection, mock_session, mock_http_client
    ):
        """Valid token does not trigger refresh API call."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_access_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token"
        ) as mock_refresh:
            await ensure_valid_access_token(
                mock_connection, mock_session, mock_http_client
            )

        mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_commit_session(
        self, mock_connection, mock_session, mock_http_client
    ):
        """Valid token does not update database."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_access_token"
        ):
            await ensure_valid_access_token(
                mock_connection, mock_session, mock_http_client
            )

        mock_session.commit.assert_not_called()


# =============================================================================
# Token Expired Tests
# =============================================================================

class TestTokenExpired:
    """Tests for when token is expired and needs refresh."""

    @pytest.mark.asyncio
    async def test_calls_refresh_and_returns_new_token(
        self, expired_connection, mock_session, mock_http_client
    ):
        """Expired token triggers refresh and returns new token."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_refresh_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            return_value={"access_token": "new_access_token", "expires_in": 3600}
        ), patch(
            "backend.core.google_token_management.encrypt_token",
            return_value=b"new_encrypted_token"
        ):
            result = await ensure_valid_access_token(
                expired_connection, mock_session, mock_http_client
            )

        assert result == {"access_token": "new_access_token"}

    @pytest.mark.asyncio
    async def test_updates_connection_in_database(
        self, expired_connection, mock_session, mock_http_client
    ):
        """Expired token refresh updates connection object and commits."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_refresh_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            return_value={"access_token": "new_access_token", "expires_in": 3600}
        ), patch(
            "backend.core.google_token_management.encrypt_token",
            return_value=b"new_encrypted_token"
        ):
            await ensure_valid_access_token(
                expired_connection, mock_session, mock_http_client
            )

        # Verify connection was updated
        assert expired_connection.encrypted_access_token == b"new_encrypted_token"
        assert expired_connection.token_expires_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_expires_at_none_triggers_refresh(
        self, mock_connection, mock_session, mock_http_client
    ):
        """Token with None expires_at triggers refresh."""
        mock_connection.token_expires_at = None

        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_refresh_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            return_value={"access_token": "new_access_token", "expires_in": 3600}
        ), patch(
            "backend.core.google_token_management.encrypt_token",
            return_value=b"new_encrypted_token"
        ):
            result = await ensure_valid_access_token(
                mock_connection, mock_session, mock_http_client
            )

        assert result == {"access_token": "new_access_token"}


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error conditions."""

    @pytest.mark.asyncio
    async def test_refresh_token_invalid_error(
        self, expired_connection, mock_session, mock_http_client
    ):
        """Invalid refresh token returns REFRESH_TOKEN_INVALID error."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_refresh_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            side_effect=ValueError("Refresh token invalid")
        ):
            result = await ensure_valid_access_token(
                expired_connection, mock_session, mock_http_client
            )

        assert result == {"error": "REFRESH_TOKEN_INVALID"}

    @pytest.mark.asyncio
    async def test_api_quota_exceeded_error(
        self, expired_connection, mock_session, mock_http_client
    ):
        """Quota exceeded returns API_QUOTA_EXCEEDED error."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_refresh_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            side_effect=ValueError("API quota exceeded")
        ):
            result = await ensure_valid_access_token(
                expired_connection, mock_session, mock_http_client
            )

        assert result == {"error": "API_QUOTA_EXCEEDED"}

    @pytest.mark.asyncio
    async def test_token_refresh_failed_on_other_error(
        self, expired_connection, mock_session, mock_http_client
    ):
        """Other refresh errors return TOKEN_REFRESH_FAILED."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_refresh_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            side_effect=Exception("Network error")
        ):
            result = await ensure_valid_access_token(
                expired_connection, mock_session, mock_http_client
            )

        assert result == {"error": "TOKEN_REFRESH_FAILED"}

    @pytest.mark.asyncio
    async def test_refresh_token_decryption_failed(
        self, expired_connection, mock_session, mock_http_client
    ):
        """Failed refresh token decryption returns TOKEN_DECRYPTION_FAILED."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            side_effect=Exception("Decryption failed")
        ):
            result = await ensure_valid_access_token(
                expired_connection, mock_session, mock_http_client
            )

        assert result == {"error": "TOKEN_DECRYPTION_FAILED"}

    @pytest.mark.asyncio
    async def test_access_token_decryption_failed(
        self, mock_connection, mock_session, mock_http_client
    ):
        """Failed access token decryption returns TOKEN_DECRYPTION_FAILED."""
        with patch(
            "backend.core.google_token_management.decrypt_token",
            side_effect=Exception("Decryption failed")
        ):
            result = await ensure_valid_access_token(
                mock_connection, mock_session, mock_http_client
            )

        assert result == {"error": "TOKEN_DECRYPTION_FAILED"}
