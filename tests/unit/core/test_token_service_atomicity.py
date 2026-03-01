"""
Tests for token service atomicity (Increment 22).

Verifies that both token exchange flows use a single atomic commit:
- exchange_authorization_code: mark used + insert token in one commit
- exchange_refresh_token: revoke old + insert new in one commit
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestAuthorizationCodeAtomicity:
    """Tests for authorization code exchange atomicity."""

    @pytest.mark.asyncio
    async def test_authcode_exchange_single_commit(self):
        """exchange_authorization_code calls db.commit() exactly once."""
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
        mock_code.used = False

        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # db.add() is synchronous

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

        # Assert exactly 1 commit call (atomic)
        assert mock_db.commit.call_count == 1, (
            f"Expected exactly 1 commit call, got {mock_db.commit.call_count}"
        )

    @pytest.mark.asyncio
    async def test_authcode_exchange_no_commit_on_token_insert_failure(self):
        """If token insert fails, db.commit() is never called."""
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
        mock_code.used = False

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        # Make db.add() raise an exception to simulate token insert failure
        # db.add() is synchronous, so use MagicMock side_effect
        mock_db.add = MagicMock(side_effect=RuntimeError("Simulated DB insert failure"))

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
            with pytest.raises(RuntimeError, match="Simulated DB insert failure"):
                await exchange_authorization_code(
                    db=mock_db,
                    code="test_auth_code",
                    code_verifier="test_verifier",
                    client_id="test-client",
                    redirect_uri="https://example.com/callback",
                    correlation_id="test-correlation"
                )

        # Assert commit was never called (transaction not committed)
        assert mock_db.commit.call_count == 0, (
            f"Expected 0 commit calls on failure, got {mock_db.commit.call_count}"
        )


class TestRefreshTokenAtomicity:
    """Tests for refresh token exchange atomicity (regression guard)."""

    @pytest.mark.asyncio
    async def test_refresh_token_exchange_single_commit(self):
        """exchange_refresh_token calls db.commit() exactly once (regression guard)."""
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token

        user_id = uuid4()

        # Create mock token
        mock_token = MagicMock()
        mock_token.user_id = user_id
        mock_token.client_id = "test-client"
        mock_token.scope = ["focused.read"]
        mock_token.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        mock_token.jti = str(uuid4())
        mock_token.revoked = False

        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # db.add() is synchronous

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_token
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

        # Assert exactly 1 commit call (atomic)
        assert mock_db.commit.call_count == 1, (
            f"Expected exactly 1 commit call, got {mock_db.commit.call_count}"
        )
