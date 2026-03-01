"""
Tests for token service row locking (Increment 21).

Tests verify that SELECT queries use FOR UPDATE to prevent concurrent
token exchange race conditions.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql


class TestRefreshTokenLocking:
    """Tests for refresh token exchange row locking."""

    @pytest.mark.asyncio
    async def test_refresh_token_exchange_uses_for_update(self):
        """exchange_refresh_token SELECT uses FOR UPDATE clause."""
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token

        # Track the executed query
        executed_queries = []

        async def capture_execute(stmt):
            executed_queries.append(stmt)
            # Return empty result to exit early
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = capture_execute

        # Call the function (will fail with "Invalid refresh token" but that's fine)
        result = await exchange_refresh_token(
            db=mock_db,
            refresh_token="test_refresh_token_12345",
            client_id="test-client",
            correlation_id="test-correlation"
        )

        # Should have executed one query
        assert len(executed_queries) == 1

        # Compile the query with PostgreSQL dialect to check FOR UPDATE
        query = executed_queries[0]
        compiled = query.compile(dialect=postgresql.dialect())
        sql_str = str(compiled)

        # Assert FOR UPDATE is in the compiled SQL
        assert "FOR UPDATE" in sql_str, f"Expected FOR UPDATE in query, got: {sql_str}"

        # Also verify the revoked filter is in the query
        assert "revoked" in sql_str.lower(), f"Expected revoked filter in query, got: {sql_str}"

    @pytest.mark.asyncio
    async def test_refresh_token_revoked_after_lock(self):
        """After exchange_refresh_token, the original token is revoked."""
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token

        user_id = uuid4()

        # Create mock token that will be returned
        mock_token = MagicMock()
        mock_token.user_id = user_id
        mock_token.client_id = "test-client"
        mock_token.scope = ["focused.read"]
        mock_token.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        mock_token.jti = str(uuid4())

        # Track revocation using simple attributes
        mock_token._revoked = False
        mock_token._revoked_at = None
        revocation_times = []

        # Use PropertyMock for revoked attribute
        revoked_mock = MagicMock()
        revoked_mock.__bool__ = lambda self: mock_token._revoked
        type(mock_token).revoked = property(
            lambda self: mock_token._revoked,
            lambda self, value: setattr(mock_token, '_revoked', value)
        )
        type(mock_token).revoked_at = property(
            lambda self: mock_token._revoked_at,
            lambda self, value: (revocation_times.append(value), setattr(mock_token, '_revoked_at', value))
        )

        mock_db = AsyncMock()

        # First call returns the token, subsequent calls for commit
        call_count = [0]
        async def mock_execute(stmt):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = mock_token
            else:
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_db.execute = mock_execute

        with patch(
            "backend.core.oauth_provider.services.token_service.create_access_token",
            return_value=("mock_access_token", str(uuid4()))
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_refresh_token",
            return_value="new_refresh_token"
        ), patch(
            "backend.core.oauth_provider.services.token_service.encrypt_token",
            return_value="encrypted_token"
        ):
            result = await exchange_refresh_token(
                db=mock_db,
                refresh_token="test_refresh_token",
                client_id="test-client",
                correlation_id="test-correlation"
            )

        # Should succeed
        assert isinstance(result, dict), f"Expected success dict, got: {result}"
        assert "access_token" in result

        # Token should be marked revoked
        assert mock_token._revoked is True, "Token should be revoked after exchange"
        assert len(revocation_times) == 1, "revoked_at should be set"
        assert revocation_times[0] is not None


class TestAuthorizationCodeLocking:
    """Tests for authorization code exchange row locking."""

    @pytest.mark.asyncio
    async def test_authorization_code_exchange_uses_for_update(self):
        """exchange_authorization_code SELECT uses FOR UPDATE clause."""
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        # Track the executed query
        executed_queries = []

        async def capture_execute(stmt):
            executed_queries.append(stmt)
            # Return empty result to exit early
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_db = AsyncMock()
        mock_db.execute = capture_execute

        # Call the function (will fail with "Invalid authorization code" but that's fine)
        result = await exchange_authorization_code(
            db=mock_db,
            code="test_auth_code",
            code_verifier="test_verifier",
            client_id="test-client",
            redirect_uri="https://example.com/callback",
            correlation_id="test-correlation"
        )

        # Should have executed one query
        assert len(executed_queries) == 1

        # Compile the query with PostgreSQL dialect to check FOR UPDATE
        query = executed_queries[0]
        compiled = query.compile(dialect=postgresql.dialect())
        sql_str = str(compiled)

        # Assert FOR UPDATE is in the compiled SQL
        assert "FOR UPDATE" in sql_str, f"Expected FOR UPDATE in query, got: {sql_str}"

    @pytest.mark.asyncio
    async def test_authorization_code_used_after_lock(self):
        """After exchange_authorization_code, the code is marked as used."""
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()

        # Create mock auth code
        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = "test-client"
        mock_code.redirect_uri = "https://example.com/callback"
        mock_code.scope = ["focused.read"]
        mock_code.code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        # Track used flag changes
        mock_code._used = False
        used_values = []

        type(mock_code).used = property(
            lambda self: mock_code._used,
            lambda self, value: (used_values.append(value), setattr(mock_code, '_used', value))
        )

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        with patch(
            "backend.core.oauth_provider.services.token_service.verify_pkce",
            return_value=True
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_access_token",
            return_value=("mock_access_token", str(uuid4()))
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_refresh_token",
            return_value="new_refresh_token"
        ), patch(
            "backend.core.oauth_provider.services.token_service.encrypt_token",
            return_value="encrypted_token"
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id="test-client",
                redirect_uri="https://example.com/callback",
                correlation_id="test-correlation"
            )

        # Should succeed
        assert isinstance(result, dict), f"Expected success dict, got: {result}"
        assert "access_token" in result

        # Code should be marked as used
        assert True in used_values, "Code should be marked as used after exchange"
