"""
Unit tests for OAuth session service (Increment 19).

Tests session CRUD operations and expiry logic.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.core.oauth_provider.services.session_service import (
    SESSION_LIFETIME_DAYS,
    SESSION_TOKEN_BYTES,
    _generate_session_token,
    cleanup_expired_sessions,
    create_session,
    delete_session,
    delete_user_sessions,
    get_session_user,
)

# Valid 64-char hex token for tests (matches format from secrets.token_hex(32))
VALID_TEST_TOKEN = "a" * 64


class TestSessionConstants:
    """Tests for session configuration constants (Increment 19 spec compliance)."""

    def test_session_lifetime_days_is_two_years(self):
        """SESSION_LIFETIME_DAYS must be 730 (2 years) per Increment 19."""
        assert SESSION_LIFETIME_DAYS == 365 * 2

    def test_session_token_bytes_is_32(self):
        """SESSION_TOKEN_BYTES must be 32 (64 hex chars) for cryptographic security."""
        assert SESSION_TOKEN_BYTES == 32


class TestGenerateSessionToken:
    """Tests for session token generation."""

    def test_token_is_correct_length(self):
        """Token should be 64 hex chars (32 bytes)."""
        token = _generate_session_token()
        assert len(token) == SESSION_TOKEN_BYTES * 2  # 64 chars

    def test_token_is_hex(self):
        """Token should be valid hexadecimal."""
        token = _generate_session_token()
        # This will raise ValueError if not valid hex
        int(token, 16)

    def test_tokens_are_unique(self):
        """Each generated token should be unique."""
        tokens = [_generate_session_token() for _ in range(100)]
        assert len(set(tokens)) == 100


class TestCreateSession:
    """Tests for session creation."""

    @pytest.mark.asyncio
    async def test_creates_session_returns_token(self):
        """create_session should return a 64-char hex token."""
        user_id = uuid4()
        mock_db = AsyncMock()

        token = await create_session(user_id, mock_db, correlation_id="test-123")

        assert len(token) == SESSION_TOKEN_BYTES * 2  # 64 chars
        # Verify hex format
        int(token, 16)

    @pytest.mark.asyncio
    async def test_creates_session_adds_to_db(self):
        """create_session should add session to database."""
        user_id = uuid4()
        mock_db = AsyncMock()

        await create_session(user_id, mock_db, correlation_id="test-123")

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_session_with_correct_expiry(self):
        """create_session should set expires_at to now + SESSION_LIFETIME_DAYS."""
        user_id = uuid4()
        mock_db = AsyncMock()

        before_call = datetime.now(timezone.utc)
        await create_session(user_id, mock_db, correlation_id="test-123")
        after_call = datetime.now(timezone.utc)

        # Inspect the added model instance
        added_session = mock_db.add.call_args[0][0]

        # Verify expires_at is approximately now + SESSION_LIFETIME_DAYS
        expected_min = before_call + timedelta(days=SESSION_LIFETIME_DAYS)
        expected_max = after_call + timedelta(days=SESSION_LIFETIME_DAYS)
        assert expected_min <= added_session.expires_at <= expected_max

    @pytest.mark.asyncio
    async def test_creates_session_with_correct_user_id(self):
        """create_session should persist the correct user_id."""
        user_id = uuid4()
        mock_db = AsyncMock()

        await create_session(user_id, mock_db, correlation_id="test-123")

        added_session = mock_db.add.call_args[0][0]
        assert added_session.user_id == user_id

    @pytest.mark.asyncio
    async def test_creates_session_with_correct_token(self):
        """create_session should persist the returned token in the session."""
        user_id = uuid4()
        mock_db = AsyncMock()

        token = await create_session(user_id, mock_db, correlation_id="test-123")

        added_session = mock_db.add.call_args[0][0]
        assert added_session.session_token == token
        assert len(added_session.session_token) == SESSION_TOKEN_BYTES * 2

    @pytest.mark.asyncio
    async def test_accepts_string_user_id(self):
        """create_session should convert string user_id to UUID."""
        user_id_str = str(uuid4())
        mock_db = AsyncMock()

        await create_session(user_id_str, mock_db, correlation_id="test-123")

        added_session = mock_db.add.call_args[0][0]
        # Verify string was converted to UUID
        from uuid import UUID
        assert isinstance(added_session.user_id, UUID)
        assert str(added_session.user_id) == user_id_str


class TestGetSessionUser:
    """Tests for session lookup."""

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_token(self):
        """get_session_user should return None for empty token."""
        mock_db = AsyncMock()

        result = await get_session_user("", mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_none_token(self):
        """get_session_user should return None for None token."""
        mock_db = AsyncMock()

        result = await get_session_user(None, mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_length_token(self):
        """get_session_user should return None for token with wrong length."""
        mock_db = AsyncMock()

        result = await get_session_user("tooshort", mock_db)

        assert result is None
        # Should not query DB for invalid token
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_for_non_string_token(self):
        """get_session_user should return None for non-string token."""
        mock_db = AsyncMock()

        result = await get_session_user(12345, mock_db)

        assert result is None
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_session_not_found(self):
        """get_session_user should return None when session doesn't exist."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_session_user(VALID_TEST_TOKEN, mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_session_expired(self):
        """get_session_user should return None when session is expired."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.user_id = uuid4()
        mock_session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)  # Expired

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await get_session_user(VALID_TEST_TOKEN, mock_db)

        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_extend_expired_session(self):
        """get_session_user should NOT update or commit for expired sessions."""
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.user_id = uuid4()
        mock_session.expires_at = datetime.now(timezone.utc) - timedelta(days=1)  # Expired

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await get_session_user(VALID_TEST_TOKEN, mock_db)

        assert result is None
        # Only one execute call (the SELECT), no UPDATE
        assert mock_db.execute.call_count == 1
        # No commit for expired sessions
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_user_id_for_valid_session(self):
        """get_session_user should return user_id for valid session."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.user_id = user_id
        mock_session.expires_at = datetime.now(timezone.utc) + timedelta(days=15)  # Valid

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await get_session_user(VALID_TEST_TOKEN, mock_db)

        assert result == user_id

    @pytest.mark.asyncio
    async def test_extends_expiry_on_valid_session(self):
        """get_session_user should extend expiry by SESSION_LIFETIME_DAYS (sliding window)."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.user_id = user_id
        # Session has some time left, but less than full lifetime
        mock_session.expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_LIFETIME_DAYS // 2)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        await get_session_user(VALID_TEST_TOKEN, mock_db)

        # Should have called execute twice: once for select, once for update
        assert mock_db.execute.call_count == 2
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sliding_window_sets_correct_expiry(self):
        """get_session_user should set new expires_at = now + SESSION_LIFETIME_DAYS."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_session = MagicMock()
        mock_session.user_id = user_id
        old_expiry = datetime.now(timezone.utc) + timedelta(days=100)
        mock_session.expires_at = old_expiry

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        # Capture the time before and after the call
        before_call = datetime.now(timezone.utc)
        await get_session_user(VALID_TEST_TOKEN, mock_db)
        after_call = datetime.now(timezone.utc)

        # Get the UPDATE statement from the second execute call
        assert mock_db.execute.call_count == 2
        update_call = mock_db.execute.call_args_list[1]
        update_stmt = update_call[0][0]

        # Extract the expires_at value from the compiled statement
        # The statement is: update(OAuthSession).where(...).values(expires_at=new_expires_at)
        compiled = update_stmt.compile()
        new_expires_at = compiled.params['expires_at']

        # Verify new expiry is approximately now + SESSION_LIFETIME_DAYS
        expected_min = before_call + timedelta(days=SESSION_LIFETIME_DAYS)
        expected_max = after_call + timedelta(days=SESSION_LIFETIME_DAYS)

        assert expected_min <= new_expires_at <= expected_max
        # Verify the new expiry is later than the old one (sliding window extends)
        assert new_expires_at > old_expiry


class TestDeleteSession:
    """Tests for session deletion."""

    @pytest.mark.asyncio
    async def test_returns_false_for_empty_token(self):
        """delete_session should return False for empty token."""
        mock_db = AsyncMock()

        result = await delete_session("", mock_db)

        assert result is False
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_for_wrong_length_token(self):
        """delete_session should return False for token with wrong length."""
        mock_db = AsyncMock()

        result = await delete_session("tooshort", mock_db)

        assert result is False
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_false_for_non_string_token(self):
        """delete_session should return False for non-string token."""
        mock_db = AsyncMock()

        result = await delete_session(12345, mock_db)

        assert result is False
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self):
        """delete_session should return True when session was deleted."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await delete_session(VALID_TEST_TOKEN, mock_db)

        assert result is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        """delete_session should return False when session not found."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await delete_session(VALID_TEST_TOKEN, mock_db)

        assert result is False


class TestDeleteUserSessions:
    """Tests for deleting all sessions for a user."""

    @pytest.mark.asyncio
    async def test_deletes_rows_and_commits(self):
        """delete_user_sessions should delete all user sessions and commit."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        deleted_count = await delete_user_sessions(user_id, mock_db, correlation_id="test-123")

        assert deleted_count == 3
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_zero_rows(self):
        """delete_user_sessions should return 0 when user has no sessions."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        deleted_count = await delete_user_sessions(user_id, mock_db)

        assert deleted_count == 0
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_accepts_string_user_id(self):
        """delete_user_sessions should accept user_id as string."""
        user_id = str(uuid4())
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_db.execute.return_value = mock_result

        deleted_count = await delete_user_sessions(user_id, mock_db)

        assert deleted_count == 2

    @pytest.mark.asyncio
    async def test_filters_by_user_id(self):
        """delete_user_sessions must filter by user_id (not delete all sessions)."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        await delete_user_sessions(user_id, mock_db)

        # Verify the DELETE statement contains user_id filter
        stmt = mock_db.execute.call_args[0][0]
        stmt_str = str(stmt)
        assert "user_id" in stmt_str
        assert "oauth_sessions" in stmt_str
        # Ensure it's a DELETE, not SELECT
        assert stmt_str.strip().upper().startswith("DELETE")


class TestCleanupExpiredSessions:
    """Tests for expired session cleanup."""

    @pytest.mark.asyncio
    async def test_deletes_expired_sessions(self):
        """cleanup_expired_sessions should delete expired sessions."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        deleted_count = await cleanup_expired_sessions(mock_db, correlation_id="test-123")

        assert deleted_count == 5
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_none_expired(self):
        """cleanup_expired_sessions should return 0 when no sessions expired."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        deleted_count = await cleanup_expired_sessions(mock_db)

        assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_filters_by_expires_at(self):
        """cleanup_expired_sessions must filter by expires_at < now (not delete all)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        await cleanup_expired_sessions(mock_db)

        # Verify the DELETE statement contains expires_at filter
        stmt = mock_db.execute.call_args[0][0]
        stmt_str = str(stmt)
        assert "expires_at" in stmt_str
        assert "oauth_sessions" in stmt_str
        # Ensure it's a DELETE, not SELECT
        assert stmt_str.strip().upper().startswith("DELETE")
