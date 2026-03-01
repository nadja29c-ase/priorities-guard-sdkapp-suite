"""
Tests for authorize endpoint state parameter validation (Increment 20).

Tests the state parameter length validation added for security hardening.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.responses import RedirectResponse


class TestStateParameterValidation:
    """Tests for state parameter length validation (Increment 20)."""

    @pytest.mark.asyncio
    async def test_state_over_512_chars_returns_error_redirect(self):
        """State over 512 characters returns error redirect without echoing state."""
        from backend.core.oauth_provider.authorize import authorize_endpoint

        # Create oversized state
        oversized_state = "x" * 513

        # Mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.headers = {"Accept-Language": "en"}

        # Mock client
        mock_client = MagicMock()
        mock_client.redirect_uris = ["https://example.com/callback"]
        mock_client.scopes = ["focused.read"]
        mock_client.provider = "Test App"

        # Mock database
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute.return_value = mock_result

        with patch(
            "backend.core.oauth_provider.authorize.check_rate_limit",
            new_callable=AsyncMock
        ):
            response = await authorize_endpoint(
                request=mock_request,
                response_type="code",
                client_id="test-client",
                redirect_uri="https://example.com/callback",
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                scope="focused.read",
                state=oversized_state,
                db=mock_db,
            )

        # Should be a redirect response
        assert isinstance(response, RedirectResponse)
        assert response.status_code == 302

        # Check redirect URL
        location = response.headers.get("location", "")
        assert "error=invalid_request" in location
        assert "state" in location.lower() and "too" in location.lower()

        # CRITICAL: Oversized state should NOT be in redirect URL
        assert oversized_state not in location

    @pytest.mark.asyncio
    async def test_state_exactly_512_chars_accepted(self):
        """State exactly 512 characters is accepted and passes validation."""
        from backend.core.oauth_provider.authorize import authorize_endpoint

        state_512 = "x" * 512

        # Mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.headers = {"Accept-Language": "en"}

        # Mock client
        mock_client = MagicMock()
        mock_client.redirect_uris = ["https://example.com/callback"]
        mock_client.scopes = ["focused.read"]
        mock_client.provider = "Test App"

        # Mock user
        mock_user = MagicMock()
        mock_user.id = uuid4()

        # Mock database
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute.return_value = mock_result

        with patch(
            "backend.core.oauth_provider.authorize.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.authorize._resolve_user_identity",
            new_callable=AsyncMock,
            return_value=mock_user
        ), patch(
            "backend.core.oauth_provider.authorize.create_authorization_context",
            new_callable=AsyncMock,
            return_value="auth-context-123"
        ), patch(
            "backend.core.oauth_provider.authorize.templates"
        ) as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()

            response = await authorize_endpoint(
                request=mock_request,
                response_type="code",
                client_id="test-client",
                redirect_uri="https://example.com/callback",
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                scope="focused.read",
                state=state_512,
                db=mock_db,
            )

        # Should render template (consent screen), not error redirect
        mock_templates.TemplateResponse.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_none_accepted(self):
        """No state parameter is accepted."""
        from backend.core.oauth_provider.authorize import authorize_endpoint

        # Mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.headers = {"Accept-Language": "en"}

        # Mock client
        mock_client = MagicMock()
        mock_client.redirect_uris = ["https://example.com/callback"]
        mock_client.scopes = ["focused.read"]
        mock_client.provider = "Test App"

        # Mock user
        mock_user = MagicMock()
        mock_user.id = uuid4()

        # Mock database
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_client
        mock_db.execute.return_value = mock_result

        with patch(
            "backend.core.oauth_provider.authorize.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.authorize._resolve_user_identity",
            new_callable=AsyncMock,
            return_value=mock_user
        ), patch(
            "backend.core.oauth_provider.authorize.create_authorization_context",
            new_callable=AsyncMock,
            return_value="auth-context-123"
        ), patch(
            "backend.core.oauth_provider.authorize.templates"
        ) as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()

            response = await authorize_endpoint(
                request=mock_request,
                response_type="code",
                client_id="test-client",
                redirect_uri="https://example.com/callback",
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                scope="focused.read",
                state=None,  # No state
                db=mock_db,
            )

        # Should render template (consent screen), not error redirect
        mock_templates.TemplateResponse.assert_called_once()
