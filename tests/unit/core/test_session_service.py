"""
Tests for OAuth session service (Increment 20 - session token hashing).

Tests the session token hashing and encryption functionality added
for security hardening.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.core.oauth_provider.services.session_service import (
    create_session,
    delete_session,
    get_session_user,
)


class TestSessionTokenHashing:
    """Tests for session token hashing (Increment 20)."""

    @pytest.mark.asyncio
    async def test_create_session_stores_hash_and_encrypted(self):
        """Create a session stores hash and encrypted token."""
        user_id = uuid4()
        mock_db = AsyncMock()

        # Capture the session object that gets added
        captured_session = None

        def capture_add(session):
            nonlocal captured_session
            captured_session = session

        mock_db.add = capture_add

        with patch(
            "backend.core.oauth_provider.services.session_service.encrypt_token",
            return_value="encrypted_token_value"
        ):
            token = await create_session(user_id, mock_db)

        # Assert token is returned (64-char hex)
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

        # Assert session object has hash and encrypted values
        assert captured_session is not None
        assert captured_session.session_token == token
        assert captured_session.session_token_hash is not None
        assert len(captured_session.session_token_hash) == 64  # SHA-256 hex
        assert captured_session.session_token_enc == "encrypted_token_value"

    @pytest.mark.asyncio
    async def test_session_token_hash_is_deterministic(self):
        """Same token produces same hash."""
        from backend.core.encryption import hash_token

        token = "a" * 64  # Simulated session token

        hash1 = hash_token(token)
        hash2 = hash_token(token)

        assert hash1 == hash2
        assert len(hash1) == 64

    @pytest.mark.asyncio
    async def test_get_session_user_by_hash(self):
        """get_session_user looks up by session_token_hash."""
        from backend.core.encryption import hash_token

        user_id = uuid4()
        token = "b" * 64
        token_hash = hash_token(token)

        # Create mock session
        mock_session = MagicMock()
        mock_session.user_id = user_id
        mock_session.id = uuid4()
        mock_session.expires_at = datetime.now(timezone.utc) + timedelta(days=1)

        # Mock database
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session
        mock_db.execute.return_value = mock_result

        result = await get_session_user(token, mock_db)

        assert result == user_id

        # Verify the query used session_token_hash
        call_args = mock_db.execute.call_args_list[0]
        query = call_args[0][0]
        # The query should contain session_token_hash in its where clause
        query_str = str(query)
        assert "session_token_hash" in query_str

    @pytest.mark.asyncio
    async def test_delete_session_by_hash(self):
        """delete_session uses session_token_hash for lookup."""
        from backend.core.encryption import hash_token

        token = "c" * 64
        token_hash = hash_token(token)

        # Mock database - simulate successful delete
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await delete_session(token, mock_db)

        assert result is True

        # Verify the query used session_token_hash
        call_args = mock_db.execute.call_args_list[0]
        # The delete statement should reference session_token_hash
        stmt = call_args[0][0]
        stmt_str = str(stmt)
        assert "session_token_hash" in stmt_str


class TestHashTokenFunction:
    """Tests for the hash_token function in encryption.py."""

    def test_hash_token_returns_64_char_hex(self):
        """hash_token returns a 64-character hex string."""
        from backend.core.encryption import hash_token

        result = hash_token("test_token")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_token_matches_hashlib(self):
        """hash_token produces same result as direct hashlib call."""
        from backend.core.encryption import hash_token

        token = "my_secret_token"
        expected = hashlib.sha256(token.encode()).hexdigest()
        result = hash_token(token)

        assert result == expected

    def test_hash_token_empty_raises(self):
        """hash_token raises ValueError for empty token."""
        from backend.core.encryption import hash_token

        with pytest.raises(ValueError, match="Token cannot be empty"):
            hash_token("")

    def test_hash_refresh_token_alias(self):
        """hash_refresh_token is an alias for hash_token."""
        from backend.core.encryption import hash_refresh_token, hash_token

        assert hash_refresh_token is hash_token


class TestSessionTokenHexValidation:
    """Tests for session token hex format validation."""

    @pytest.mark.asyncio
    async def test_get_session_user_rejects_non_hex_token(self):
        """get_session_user returns None for non-hex characters without querying DB."""
        mock_db = AsyncMock()

        # "Z" is not a valid hex character
        result = await get_session_user("Z" * 64, mock_db)

        assert result is None
        # DB should never be called
        assert mock_db.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_get_session_user_rejects_uppercase_hex(self):
        """get_session_user returns None for uppercase hex (secrets.token_hex produces lowercase)."""
        mock_db = AsyncMock()

        # Uppercase "A" should be rejected
        result = await get_session_user("A" * 64, mock_db)

        assert result is None
        # DB should never be called
        assert mock_db.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_delete_session_rejects_non_hex_token(self):
        """delete_session returns False for non-hex characters without querying DB."""
        mock_db = AsyncMock()

        # "!" is not a valid hex character
        result = await delete_session("!" * 64, mock_db)

        assert result is False
        # DB should never be called
        assert mock_db.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_get_session_user_accepts_valid_hex(self):
        """get_session_user queries DB for valid 64-char lowercase hex token."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Session not found
        mock_db.execute.return_value = mock_result

        # Valid lowercase hex token
        valid_token = "0123456789abcdef" * 4  # 64 chars

        result = await get_session_user(valid_token, mock_db)

        # Session not found, but DB WAS called (guard passed)
        assert result is None
        assert mock_db.execute.call_count >= 1
