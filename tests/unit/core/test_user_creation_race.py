"""
Tests for user creation race condition handling (Increment 23).

Tests the IntegrityError handling in _resolve_user_identity when
concurrent requests try to create the same user.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError


class TestUserCreationRace:
    """Tests for concurrent user creation handling."""

    @pytest.mark.asyncio
    async def test_concurrent_login_hint_second_request_succeeds(self):
        """Second concurrent request recovers after IntegrityError."""
        from backend.core.oauth_provider.authorize import _resolve_user_identity

        chatgpt_user_id = "chatgpt-user-12345"
        user_id = uuid4()

        # Create mock user that will be returned after race recovery
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.chatgpt_user_id = chatgpt_user_id

        # Mock request
        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"

        # Mock db
        mock_db = AsyncMock()

        # Track call sequence
        execute_calls = []

        async def mock_execute(stmt):
            execute_calls.append("execute")
            mock_result = MagicMock()
            # First execute (initial SELECT) returns None
            # Second execute (re-fetch after race) returns the user
            if len(execute_calls) == 1:
                mock_result.scalar_one_or_none.return_value = None
            else:
                mock_result.scalar_one.return_value = mock_user
            return mock_result

        mock_db.execute = mock_execute
        mock_db.add = MagicMock()

        # Make commit raise IntegrityError (simulating losing racer)
        mock_db.commit = AsyncMock(side_effect=IntegrityError("stmt", "params", "orig"))

        with patch(
            "backend.core.oauth_provider.authorize.get_session_cookie",
            return_value=None
        ):
            result = await _resolve_user_identity(
                mock_request, mock_db, chatgpt_user_id, "test-correlation"
            )

        # Should have called rollback exactly once
        assert mock_db.rollback.call_count == 1
        mock_db.refresh.assert_not_called()

        # Should return a valid user
        assert result is not None
        assert result.chatgpt_user_id == chatgpt_user_id

        # Should have called execute twice (initial SELECT + re-fetch)
        assert len(execute_calls) == 2

    @pytest.mark.asyncio
    async def test_normal_first_time_user_no_race(self):
        """Normal first-time user creation without race condition."""
        from backend.core.oauth_provider.authorize import _resolve_user_identity

        chatgpt_user_id = "chatgpt-user-67890"
        user_id = uuid4()

        # Create mock user
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.chatgpt_user_id = chatgpt_user_id

        # Mock request
        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"

        # Mock db
        mock_db = AsyncMock()

        # Initial SELECT returns None (user doesn't exist)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Capture the user object passed to db.add()
        added_user = None

        def capture_add(user):
            nonlocal added_user
            added_user = user

        mock_db.add = MagicMock(side_effect=capture_add)

        # Commit succeeds normally
        mock_db.commit = AsyncMock()

        # Refresh populates the mock user
        async def mock_refresh(user):
            user.id = user_id

        mock_db.refresh = mock_refresh

        with patch(
            "backend.core.oauth_provider.authorize.get_session_cookie",
            return_value=None
        ):
            result = await _resolve_user_identity(
                mock_request, mock_db, chatgpt_user_id, "test-correlation"
            )

        # rollback should NOT have been called
        mock_db.rollback.assert_not_called()

        # db.add() should have been called
        mock_db.add.assert_called_once()

        # db.commit() should have been called exactly once
        mock_db.commit.assert_called_once()

        # Should return a user with correct chatgpt_user_id
        assert added_user is not None
        assert added_user.chatgpt_user_id == chatgpt_user_id

    @pytest.mark.asyncio
    async def test_existing_user_no_insert_attempted(self):
        """Existing user found by login_hint - no INSERT attempted."""
        from backend.core.oauth_provider.authorize import _resolve_user_identity

        chatgpt_user_id = "chatgpt-user-existing"
        user_id = uuid4()

        # Create mock existing user
        mock_user = MagicMock()
        mock_user.id = user_id
        mock_user.chatgpt_user_id = chatgpt_user_id

        # Mock request
        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"

        # Mock db
        mock_db = AsyncMock()

        # Initial SELECT returns existing user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute.return_value = mock_result

        with patch(
            "backend.core.oauth_provider.authorize.get_session_cookie",
            return_value=None
        ):
            result = await _resolve_user_identity(
                mock_request, mock_db, chatgpt_user_id, "test-correlation"
            )

        # db.add() should NOT have been called
        mock_db.add.assert_not_called()

        # db.commit() should NOT have been called (no write needed)
        mock_db.commit.assert_not_called()

        # Should return the existing user
        assert result is mock_user
        assert result.chatgpt_user_id == chatgpt_user_id
