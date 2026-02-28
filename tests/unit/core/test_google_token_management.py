"""
Unit tests for google_token_management module.

Tests ensure_valid_access_token() behavior for token expiry,
refresh logic, error handling, and concurrent refresh protection.
"""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.core.google_token_management import (
    ensure_valid_access_token,
    _user_refresh_locks,
)


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
        mock_session.refresh.assert_called_once_with(mock_connection)

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


# =============================================================================
# Concurrent Refresh Tests
# =============================================================================

class TestConcurrentRefresh:
    """Tests for concurrent token refresh protection."""

    @pytest.fixture(autouse=True)
    def clear_locks(self):
        """Clear locks before each test."""
        _user_refresh_locks.clear()
        yield
        _user_refresh_locks.clear()

    @pytest.mark.asyncio
    async def test_concurrent_refresh_only_calls_google_once(self):
        """Two concurrent calls for same user only make one Google API call."""
        # Track how many times refresh_access_token is called
        refresh_call_count = 0

        async def mock_refresh(*args, **kwargs):
            nonlocal refresh_call_count
            refresh_call_count += 1
            # Simulate network latency to ensure both coroutines reach the lock
            await asyncio.sleep(0.01)
            return {"access_token": "new_token", "expires_in": 3600}

        # Create two separate connections (simulating two requests loading same DB row)
        def make_expired_connection():
            conn = MagicMock()
            conn.user_id = "user-123"
            conn.encrypted_refresh_token = b"encrypted_refresh"
            conn.encrypted_access_token = b"encrypted_access"
            conn.token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            return conn

        connection1 = make_expired_connection()
        connection2 = make_expired_connection()

        # Event signaling first caller's commit (set while still holding lock)
        first_commit_done = asyncio.Event()

        # Mock session.refresh to update token_expires_at for second caller
        # (simulating DB read after first caller's commit)
        async def mock_session_refresh(conn):
            # After first caller commits, second caller sees fresh token
            if first_commit_done.is_set():
                conn.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        # session1.commit sets the event (while still holding lock)
        async def mock_session1_commit():
            first_commit_done.set()

        session1 = AsyncMock()
        session1.refresh = mock_session_refresh
        session1.commit = mock_session1_commit

        session2 = AsyncMock()
        session2.refresh = mock_session_refresh

        http_client = AsyncMock()

        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            side_effect=mock_refresh
        ), patch(
            "backend.core.google_token_management.encrypt_token",
            return_value=b"new_encrypted"
        ):
            # Launch both concurrently
            results = await asyncio.gather(
                ensure_valid_access_token(connection1, session1, http_client),
                ensure_valid_access_token(connection2, session2, http_client)
            )

        # Should only call refresh once
        assert refresh_call_count == 1

        # Both calls should return valid token
        assert "access_token" in results[0]
        assert "access_token" in results[1]

    @pytest.mark.asyncio
    async def test_second_caller_gets_refreshed_token(self):
        """Second concurrent caller gets token refreshed by first caller."""
        # Create expired connection
        connection = MagicMock()
        connection.user_id = "user-456"
        connection.encrypted_refresh_token = b"encrypted_refresh"
        connection.encrypted_access_token = b"encrypted_access"
        connection.token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        session = AsyncMock()
        http_client = AsyncMock()

        # Track decrypt calls
        decrypt_calls = []

        def mock_decrypt(token):
            decrypt_calls.append(token)
            if token == b"new_encrypted":
                return "refreshed_access_token"
            return "decrypted_token"

        # After session.refresh, token is valid (simulating another coroutine's commit)
        async def mock_session_refresh(conn):
            conn.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            conn.encrypted_access_token = b"new_encrypted"

        session.refresh = mock_session_refresh

        with patch(
            "backend.core.google_token_management.decrypt_token",
            side_effect=mock_decrypt
        ), patch(
            "backend.core.google_token_management.refresh_access_token"
        ) as mock_refresh:
            result = await ensure_valid_access_token(connection, session, http_client)

        # Should not call refresh (token was valid after session.refresh)
        mock_refresh.assert_not_called()

        # Should return the refreshed token
        assert result == {"access_token": "refreshed_access_token"}

    @pytest.mark.asyncio
    async def test_lock_does_not_block_different_users(self):
        """Concurrent refreshes for different users run independently."""
        refresh_call_count = 0

        async def mock_refresh(*args, **kwargs):
            nonlocal refresh_call_count
            refresh_call_count += 1
            await asyncio.sleep(0.01)
            return {"access_token": f"token_{refresh_call_count}", "expires_in": 3600}

        def make_expired_connection(user_id):
            conn = MagicMock()
            conn.user_id = user_id
            conn.encrypted_refresh_token = b"encrypted_refresh"
            conn.encrypted_access_token = b"encrypted_access"
            conn.token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            return conn

        connection1 = make_expired_connection("user-A")
        connection2 = make_expired_connection("user-B")

        session1 = AsyncMock()
        session2 = AsyncMock()
        http_client = AsyncMock()

        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_token"
        ), patch(
            "backend.core.google_token_management.refresh_access_token",
            side_effect=mock_refresh
        ), patch(
            "backend.core.google_token_management.encrypt_token",
            return_value=b"new_encrypted"
        ):
            results = await asyncio.gather(
                ensure_valid_access_token(connection1, session1, http_client),
                ensure_valid_access_token(connection2, session2, http_client)
            )

        # Should call refresh twice (once per user)
        assert refresh_call_count == 2

        # Both should succeed
        assert "access_token" in results[0]
        assert "access_token" in results[1]

    @pytest.mark.asyncio
    async def test_lock_cleanup_on_overflow(self, mock_http_client):
        """Lock dict is cleared when it exceeds 10000 entries."""
        # Populate with 10001 entries
        for i in range(10001):
            _user_refresh_locks[f"user-{i}"] = asyncio.Lock()

        assert len(_user_refresh_locks) == 10001

        # Create a connection for a new user
        connection = MagicMock()
        connection.user_id = "new-user"
        connection.encrypted_access_token = b"encrypted_access"
        connection.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        session = AsyncMock()

        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_token"
        ):
            await ensure_valid_access_token(connection, session, mock_http_client)

        # Dict should have been cleared and new lock created
        assert len(_user_refresh_locks) == 1
        assert "new-user" in _user_refresh_locks
