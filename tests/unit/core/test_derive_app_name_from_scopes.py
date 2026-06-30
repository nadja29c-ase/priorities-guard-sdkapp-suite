"""
Unit tests for _derive_app_name_from_scopes function.

Tests verify correct app name derivation from OAuth scopes for GDPR audit trail.

v2 update (inc_consent_template_fallthrough_guard):
- _derive_app_name_from_scopes is now ONLY used as fallback for auth contexts
  created by older deploys that don't have the app_name field.
- clarity.* returns "mindsort" (not "clarity")
- Unknown/empty scopes return "unknown" (not "focused")
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.core.oauth_provider.consent_ui import _derive_app_name_from_scopes


class TestDeriveAppNameFromScopes:
    """Unit tests for scope-to-app-name derivation (v2 fallback behavior)."""

    def test_pg_scope_returns_priority_guardian(self):
        """pg.* scopes return 'priority_guardian'."""
        assert _derive_app_name_from_scopes(["pg.access"]) == "priority_guardian"

    def test_clarity_scope_returns_mindsort(self):
        """clarity.* scopes return 'mindsort' (app name, not scope prefix)."""
        assert _derive_app_name_from_scopes(["clarity.write"]) == "mindsort"

    def test_focused_scope_returns_focused(self):
        """focused.* scopes return 'focused'."""
        assert _derive_app_name_from_scopes(["focused.read"]) == "focused"
        assert _derive_app_name_from_scopes(["focused.write"]) == "focused"
        assert _derive_app_name_from_scopes(["focused.notify"]) == "focused"

    def test_multiple_focused_scopes_returns_focused(self):
        """Multiple focused.* scopes return 'focused'."""
        assert _derive_app_name_from_scopes(["focused.read", "focused.write"]) == "focused"

    def test_empty_scopes_returns_unknown(self):
        """Empty scope list returns 'unknown' (v2 fix - was 'focused' in v1)."""
        assert _derive_app_name_from_scopes([]) == "unknown"

    def test_unknown_scopes_return_unknown(self):
        """Unknown scopes return 'unknown' (v2 fix - was 'focused' in v1)."""
        assert _derive_app_name_from_scopes(["openid", "profile"]) == "unknown"

    def test_mixed_scopes_first_match_wins(self):
        """Mixed scopes use first matching prefix in list order."""
        # pg.* appears first in the list, so it wins
        assert _derive_app_name_from_scopes(["pg.access", "focused.read"]) == "priority_guardian"
        # clarity.* appears first, returns mindsort
        assert _derive_app_name_from_scopes(["clarity.write", "focused.read"]) == "mindsort"
        # Unknown scopes are skipped, first known match wins
        assert _derive_app_name_from_scopes(["openid", "pg.access", "focused.read"]) == "priority_guardian"

    def test_pg_in_list_before_focused_wins(self):
        """pg.* scope wins when it appears before focused.* in list."""
        assert _derive_app_name_from_scopes(["pg.access", "focused.read"]) == "priority_guardian"
        # Order matters - focused first means it wins
        assert _derive_app_name_from_scopes(["focused.read", "pg.access"]) == "focused"

    def test_clarity_in_list_before_focused_wins(self):
        """clarity.* scope wins when it appears before focused.* in list."""
        assert _derive_app_name_from_scopes(["clarity.write", "focused.read"]) == "mindsort"
        # Order matters - focused first means it wins
        assert _derive_app_name_from_scopes(["focused.read", "clarity.write"]) == "focused"


class TestRecordConsentAppNameIntegration:
    """
    Integration tests verifying record_consent receives correct app_name.

    v2 note: These tests now simulate auth contexts WITH app_name (new deploy)
    or WITHOUT app_name (old deploy fallback). The fallback path exercises
    _derive_app_name_from_scopes.
    """

    @pytest.mark.asyncio
    async def test_pg_scopes_with_app_name_uses_context_value(self):
        """
        PG scopes with app_name in context uses context value directly.

        v2: New deploys thread app_name from authorize.py.
        """
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-123",
            "action": "allow"
        })
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        mock_db = AsyncMock()

        # Auth context WITH app_name (new deploy)
        mock_auth_context = {
            "client_id": "test-client",
            "user_id": "test-user",
            "scope": "pg.access",
            "redirect_uri": "https://example.com/callback",
            "code_challenge": "challenge123",
            "code_challenge_method": "S256",
            "state": "state123",
            "nonce": None,
            "app_name": "priority_guardian",  # v2: threaded from authorize
        }

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
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
        assert call_kwargs["app_name"] == "priority_guardian"
        assert call_kwargs["scopes"] == ["pg.access"]

    @pytest.mark.asyncio
    async def test_clarity_scopes_with_app_name_uses_context_value(self):
        """
        Clarity scopes with app_name in context uses context value directly.

        v2: app_name="mindsort" (not "clarity").
        """
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-123",
            "action": "allow"
        })
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

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
            "app_name": "mindsort",  # v2: threaded from authorize
        }

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
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
        assert call_kwargs["app_name"] == "mindsort"
        assert call_kwargs["scopes"] == ["clarity.write"]

    @pytest.mark.asyncio
    async def test_focused_scopes_with_app_name_uses_context_value(self):
        """
        Focused scopes with app_name in context uses context value directly.
        """
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-123",
            "action": "allow"
        })
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

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
            "app_name": "focused",  # v2: threaded from authorize
        }

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
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

    @pytest.mark.asyncio
    async def test_fallback_derives_from_scopes_when_no_app_name(self):
        """
        Fallback path: context without app_name derives from scopes.

        This simulates old deploy during rolling update window.
        """
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-123",
            "action": "allow"
        })
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        mock_db = AsyncMock()

        # Auth context WITHOUT app_name (old deploy)
        mock_auth_context = {
            "client_id": "test-client",
            "user_id": "test-user",
            "scope": "pg.access",
            "redirect_uri": "https://example.com/callback",
            "code_challenge": "challenge123",
            "code_challenge_method": "S256",
            "state": "state123",
            "nonce": None,
            # NO app_name key
        }

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
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

        # Falls back to _derive_app_name_from_scopes
        mock_record_consent.assert_called_once()
        call_kwargs = mock_record_consent.call_args.kwargs
        assert call_kwargs["app_name"] == "priority_guardian"
        assert call_kwargs["scopes"] == ["pg.access"]
