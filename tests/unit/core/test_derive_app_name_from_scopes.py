"""
Unit tests for _derive_app_name_from_scopes function.

Tests verify correct app name derivation from OAuth scopes for GDPR audit trail.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.core.oauth_provider.consent_ui import _derive_app_name_from_scopes


class TestDeriveAppNameFromScopes:
    """Unit tests for scope-to-app-name derivation."""

    def test_pg_scope_returns_priority_guardian(self):
        """pg.* scopes return 'priority_guardian'."""
        assert _derive_app_name_from_scopes(["pg.access"]) == "priority_guardian"

    def test_clarity_scope_returns_clarity(self):
        """clarity.* scopes return 'clarity'."""
        assert _derive_app_name_from_scopes(["clarity.write"]) == "clarity"

    def test_focused_scope_returns_focused(self):
        """focused.* scopes return 'focused'."""
        assert _derive_app_name_from_scopes(["focused.read"]) == "focused"
        assert _derive_app_name_from_scopes(["focused.write"]) == "focused"
        assert _derive_app_name_from_scopes(["focused.notify"]) == "focused"

    def test_multiple_focused_scopes_returns_focused(self):
        """Multiple focused.* scopes return 'focused'."""
        assert _derive_app_name_from_scopes(["focused.read", "focused.write"]) == "focused"

    def test_empty_scopes_returns_focused(self):
        """Empty scope list defaults to 'focused'."""
        assert _derive_app_name_from_scopes([]) == "focused"

    def test_unknown_scopes_return_focused(self):
        """Unknown scopes default to 'focused'."""
        assert _derive_app_name_from_scopes(["openid", "profile"]) == "focused"

    def test_mixed_scopes_first_match_wins(self):
        """Mixed scopes use first matching prefix (pg > clarity > focused)."""
        # pg.* appears first in iteration, so it wins
        assert _derive_app_name_from_scopes(["openid", "pg.access", "focused.read"]) == "priority_guardian"
        assert _derive_app_name_from_scopes(["openid", "clarity.write", "focused.read"]) == "clarity"

    def test_pg_takes_precedence_over_focused(self):
        """pg.* scope wins when mixed with focused.*."""
        assert _derive_app_name_from_scopes(["focused.read", "pg.access"]) == "priority_guardian"

    def test_clarity_takes_precedence_over_focused(self):
        """clarity.* scope wins when mixed with focused.*."""
        assert _derive_app_name_from_scopes(["focused.read", "clarity.write"]) == "clarity"


class TestRecordConsentAppNameIntegration:
    """Integration tests verifying record_consent receives correct app_name."""

    @pytest.mark.asyncio
    async def test_pg_scopes_pass_priority_guardian_to_record_consent(self):
        """PG scopes result in app_name='priority_guardian' passed to record_consent."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        # Mock all dependencies
        mock_request = MagicMock()
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-123",
            "action": "allow"
        })

        mock_db = AsyncMock()

        # Mock auth context with PG scopes
        mock_auth_context = {
            "client_id": "test-client",
            "user_id": "test-user",
            "scope": "pg.access",
            "redirect_uri": "https://example.com/callback",
            "code_challenge": "challenge123",
            "code_challenge_method": "S256",
            "state": "state123",
            "nonce": None,
        }

        with patch(
            "backend.core.oauth_provider.consent_ui.get_authorization_context",
            new_callable=AsyncMock,
            return_value=mock_auth_context
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_authorization_code",
            new_callable=AsyncMock,
            return_value="auth-code-123"
        ), patch(
            "backend.core.oauth_provider.consent_ui.record_consent",
            new_callable=AsyncMock
        ) as mock_record_consent, patch(
            "backend.core.oauth_provider.consent_ui.get_session_cookie",
            return_value=None
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_session",
            new_callable=AsyncMock,
            return_value="session-token"
        ), patch(
            "backend.core.oauth_provider.consent_ui.set_session_cookie"
        ):
            response = await consent_endpoint(mock_request, mock_db)

        # Verify record_consent was called with app_name="priority_guardian"
        mock_record_consent.assert_called_once()
        call_kwargs = mock_record_consent.call_args.kwargs
        assert call_kwargs["app_name"] == "priority_guardian"
        assert call_kwargs["scopes"] == ["pg.access"]

    @pytest.mark.asyncio
    async def test_clarity_scopes_pass_clarity_to_record_consent(self):
        """Clarity scopes result in app_name='clarity' passed to record_consent."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        mock_request = MagicMock()
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-123",
            "action": "allow"
        })

        mock_db = AsyncMock()

        mock_auth_context = {
            "client_id": "test-client",
            "user_id": "test-user",
            "scope": "clarity.write",
            "redirect_uri": "https://example.com/callback",
            "code_challenge": "challenge123",
            "code_challenge_method": "S256",
            "state": "state123",
            "nonce": None,
        }

        with patch(
            "backend.core.oauth_provider.consent_ui.get_authorization_context",
            new_callable=AsyncMock,
            return_value=mock_auth_context
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_authorization_code",
            new_callable=AsyncMock,
            return_value="auth-code-123"
        ), patch(
            "backend.core.oauth_provider.consent_ui.record_consent",
            new_callable=AsyncMock
        ) as mock_record_consent, patch(
            "backend.core.oauth_provider.consent_ui.get_session_cookie",
            return_value=None
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_session",
            new_callable=AsyncMock,
            return_value="session-token"
        ), patch(
            "backend.core.oauth_provider.consent_ui.set_session_cookie"
        ):
            response = await consent_endpoint(mock_request, mock_db)

        mock_record_consent.assert_called_once()
        call_kwargs = mock_record_consent.call_args.kwargs
        assert call_kwargs["app_name"] == "clarity"
        assert call_kwargs["scopes"] == ["clarity.write"]

    @pytest.mark.asyncio
    async def test_focused_scopes_pass_focused_to_record_consent(self):
        """Focused scopes result in app_name='focused' passed to record_consent."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        mock_request = MagicMock()
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-123",
            "action": "allow"
        })

        mock_db = AsyncMock()

        mock_auth_context = {
            "client_id": "test-client",
            "user_id": "test-user",
            "scope": "focused.read focused.write",
            "redirect_uri": "https://example.com/callback",
            "code_challenge": "challenge123",
            "code_challenge_method": "S256",
            "state": "state123",
            "nonce": None,
        }

        with patch(
            "backend.core.oauth_provider.consent_ui.get_authorization_context",
            new_callable=AsyncMock,
            return_value=mock_auth_context
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_authorization_code",
            new_callable=AsyncMock,
            return_value="auth-code-123"
        ), patch(
            "backend.core.oauth_provider.consent_ui.record_consent",
            new_callable=AsyncMock
        ) as mock_record_consent, patch(
            "backend.core.oauth_provider.consent_ui.get_session_cookie",
            return_value=None
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_session",
            new_callable=AsyncMock,
            return_value="session-token"
        ), patch(
            "backend.core.oauth_provider.consent_ui.set_session_cookie"
        ):
            response = await consent_endpoint(mock_request, mock_db)

        mock_record_consent.assert_called_once()
        call_kwargs = mock_record_consent.call_args.kwargs
        assert call_kwargs["app_name"] == "focused"
        assert call_kwargs["scopes"] == ["focused.read", "focused.write"]
