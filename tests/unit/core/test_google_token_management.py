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
    _evict_stale_locks,
    LOCK_TTL_SECONDS,
    MAX_LOCK_ENTRIES,
    EVICTION_TARGET_RATIO,
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
        """Stale locks are evicted when dict exceeds capacity."""
        # Use small constants for testing
        with patch("backend.core.google_token_management.MAX_LOCK_ENTRIES", 10), \
             patch("backend.core.google_token_management.LOCK_TTL_SECONDS", 30), \
             patch("backend.core.google_token_management.EVICTION_TARGET_RATIO", 0.8):

            # Populate with 10 stale entries (old timestamps)
            stale_time = 0.0  # Very old timestamp
            for i in range(10):
                _user_refresh_locks[f"user-{i}"] = (asyncio.Lock(), stale_time)

            assert len(_user_refresh_locks) == 10

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

            # Stale entries should be evicted, new entry should exist
            assert "new-user" in _user_refresh_locks
            # All stale entries should be gone (TTL eviction)
            assert len(_user_refresh_locks) == 1


# =============================================================================
# Lock Eviction Tests (Increment 35B)
# =============================================================================

class TestLockEviction:
    """Tests for TTL-based lock eviction (ADR-002)."""

    @pytest.fixture(autouse=True)
    def clear_locks(self):
        """Clear locks before and after each test."""
        _user_refresh_locks.clear()
        yield
        _user_refresh_locks.clear()

    def test_stale_lock_evicted_on_overflow(self, monkeypatch):
        """Stale entries are evicted when inserting a new key at capacity."""
        # Use small constants for testing
        monkeypatch.setattr("backend.core.google_token_management.MAX_LOCK_ENTRIES", 10)
        monkeypatch.setattr("backend.core.google_token_management.LOCK_TTL_SECONDS", 30)
        monkeypatch.setattr("backend.core.google_token_management.EVICTION_TARGET_RATIO", 0.8)

        # Mock time.monotonic to return controlled values
        current_time = 1000.0
        monkeypatch.setattr("backend.core.google_token_management.time.monotonic", lambda: current_time)

        # Populate with exactly MAX_LOCK_ENTRIES stale entries
        stale_time = current_time - 100  # 100 seconds old (> 30s TTL)
        for i in range(10):
            _user_refresh_locks[f"user-{i}"] = (asyncio.Lock(), stale_time)

        assert len(_user_refresh_locks) == 10

        # Trigger eviction by calling the function directly
        _evict_stale_locks()

        # All stale entries should be removed
        assert len(_user_refresh_locks) == 0

    def test_fresh_lock_not_evicted_but_hard_cap_applies(self, monkeypatch):
        """Fresh entries trigger hard cap fallback when at capacity."""
        monkeypatch.setattr("backend.core.google_token_management.MAX_LOCK_ENTRIES", 10)
        monkeypatch.setattr("backend.core.google_token_management.LOCK_TTL_SECONDS", 30)
        monkeypatch.setattr("backend.core.google_token_management.EVICTION_TARGET_RATIO", 0.8)

        current_time = 1000.0
        monkeypatch.setattr("backend.core.google_token_management.time.monotonic", lambda: current_time)

        # Populate with exactly MAX_LOCK_ENTRIES fresh entries
        # (all within TTL, so TTL pass won't evict them)
        fresh_time = current_time - 10  # 10 seconds old (< 30s TTL)
        for i in range(10):
            _user_refresh_locks[f"user-{i}"] = (asyncio.Lock(), fresh_time + i * 0.1)

        assert len(_user_refresh_locks) == 10

        # Trigger eviction
        _evict_stale_locks()

        # Hard cap pass should evict oldest entries down to 80% (8 entries)
        assert len(_user_refresh_locks) == 8
        # Newest entries should survive
        assert "user-9" in _user_refresh_locks
        assert "user-8" in _user_refresh_locks

    def test_held_lock_never_evicted(self, monkeypatch):
        """Locks that are currently held are never evicted."""
        monkeypatch.setattr("backend.core.google_token_management.MAX_LOCK_ENTRIES", 10)
        monkeypatch.setattr("backend.core.google_token_management.LOCK_TTL_SECONDS", 30)
        monkeypatch.setattr("backend.core.google_token_management.EVICTION_TARGET_RATIO", 0.8)

        current_time = 1000.0
        monkeypatch.setattr("backend.core.google_token_management.time.monotonic", lambda: current_time)

        # Populate with stale entries
        stale_time = current_time - 100  # Stale
        for i in range(10):
            _user_refresh_locks[f"user-{i}"] = (asyncio.Lock(), stale_time)

        # Mark one lock as held (set internal state for testing)
        held_lock = _user_refresh_locks["user-5"][0]
        held_lock._locked = True

        try:
            # Trigger eviction
            _evict_stale_locks()

            # Held lock should survive, all others evicted
            assert len(_user_refresh_locks) == 1
            assert "user-5" in _user_refresh_locks
        finally:
            held_lock._locked = False

    def test_timestamp_updated_on_access(self, monkeypatch):
        """Timestamp is updated when accessing an existing lock entry."""
        times = [1000.0, 2000.0]
        time_index = [0]

        def mock_monotonic():
            result = times[time_index[0]]
            time_index[0] = min(time_index[0] + 1, len(times) - 1)
            return result

        monkeypatch.setattr("backend.core.google_token_management.time.monotonic", mock_monotonic)

        # Create initial entry at t=1000.0
        lock = asyncio.Lock()
        _user_refresh_locks["user-123"] = (lock, 1000.0)

        # Import and call the function that updates timestamps
        from backend.core.google_token_management import ensure_valid_access_token

        # Create a mock connection for the same user
        connection = MagicMock()
        connection.user_id = "user-123"
        connection.encrypted_access_token = b"encrypted_access"
        connection.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        session = AsyncMock()
        http_client = AsyncMock()

        # Run the function - this should update the timestamp
        import asyncio as aio
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_token"
        ):
            aio.get_event_loop().run_until_complete(
                ensure_valid_access_token(connection, session, http_client)
            )

        # Timestamp should be updated to 2000.0
        _, last_used = _user_refresh_locks["user-123"]
        assert last_used == 2000.0

    def test_eviction_does_not_run_below_threshold(self, monkeypatch):
        """Eviction is not triggered when dict is below MAX_LOCK_ENTRIES."""
        monkeypatch.setattr("backend.core.google_token_management.MAX_LOCK_ENTRIES", 10)
        monkeypatch.setattr("backend.core.google_token_management.LOCK_TTL_SECONDS", 30)

        current_time = 1000.0
        monkeypatch.setattr("backend.core.google_token_management.time.monotonic", lambda: current_time)

        # Populate with 9 stale entries (below capacity)
        stale_time = current_time - 100  # Stale
        for i in range(9):
            _user_refresh_locks[f"user-{i}"] = (asyncio.Lock(), stale_time)

        assert len(_user_refresh_locks) == 9

        # Create a connection for a new user
        connection = MagicMock()
        connection.user_id = "new-user"
        connection.encrypted_access_token = b"encrypted_access"
        connection.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        session = AsyncMock()
        http_client = AsyncMock()

        # Access should NOT trigger eviction (below threshold)
        import asyncio as aio
        with patch(
            "backend.core.google_token_management.decrypt_token",
            return_value="decrypted_token"
        ):
            aio.get_event_loop().run_until_complete(
                ensure_valid_access_token(connection, session, http_client)
            )

        # All 9 stale entries should still exist + the new entry
        assert len(_user_refresh_locks) == 10
        assert "new-user" in _user_refresh_locks
        for i in range(9):
            assert f"user-{i}" in _user_refresh_locks

    def test_no_insert_when_at_cap_and_all_held(self, monkeypatch):
        """When all locks are held, new entry uses local lock (not stored)."""
        monkeypatch.setattr("backend.core.google_token_management.MAX_LOCK_ENTRIES", 5)
        monkeypatch.setattr("backend.core.google_token_management.LOCK_TTL_SECONDS", 30)
        monkeypatch.setattr("backend.core.google_token_management.EVICTION_TARGET_RATIO", 0.8)

        current_time = 1000.0
        monkeypatch.setattr("backend.core.google_token_management.time.monotonic", lambda: current_time)

        # Populate with entries and mark all locks as held
        fresh_time = current_time - 10  # Fresh (within TTL)
        held_locks = []
        for i in range(5):
            lock = asyncio.Lock()
            lock._locked = True  # Mark as held for testing
            held_locks.append(lock)
            _user_refresh_locks[f"user-{i}"] = (lock, fresh_time)

        assert len(_user_refresh_locks) == 5

        try:
            # Create a connection for a new user
            connection = MagicMock()
            connection.user_id = "new-user"
            connection.encrypted_access_token = b"encrypted_access"
            connection.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            session = AsyncMock()
            http_client = AsyncMock()

            import asyncio as aio
            with patch(
                "backend.core.google_token_management.decrypt_token",
                return_value="decrypted_token"
            ):
                result = aio.get_event_loop().run_until_complete(
                    ensure_valid_access_token(connection, session, http_client)
                )

            # Function should still succeed (uses local lock)
            assert result == {"access_token": "decrypted_token"}

            # Dict size should be unchanged (no new entry inserted)
            assert len(_user_refresh_locks) == 5
            assert "new-user" not in _user_refresh_locks
        finally:
            # Clear held state
            for lock in held_locks:
                lock._locked = False
