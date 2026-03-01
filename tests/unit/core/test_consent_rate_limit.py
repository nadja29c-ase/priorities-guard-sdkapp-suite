"""
Tests for consent endpoint rate limiting (Increment 20).

Tests the IP-based rate limiting added for security hardening.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from backend.core.rate_limit import RateLimitExceeded


class TestConsentRateLimit:
    """Tests for consent endpoint rate limiting (Increment 20)."""

    @pytest.mark.asyncio
    async def test_consent_rate_limited_by_ip(self):
        """Consent endpoint raises RateLimitExceeded when rate limited."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        # Mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"

        mock_db = AsyncMock()

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock,
            side_effect=RateLimitExceeded("Rate limit exceeded")
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_client_ip",
            return_value="192.168.1.1"
        ):
            with pytest.raises(RateLimitExceeded):
                await consent_endpoint(mock_request, mock_db)

    @pytest.mark.asyncio
    async def test_consent_rate_limit_uses_correct_key(self):
        """Rate limit check uses correct key format."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        # Track the rate limit call
        rate_limit_calls = []

        async def mock_check_rate_limit(key, limit, window, request):
            rate_limit_calls.append({"key": key, "limit": limit, "window": window})

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-id",
            "action": "allow",
        })

        mock_db = AsyncMock()

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            side_effect=mock_check_rate_limit
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_client_ip",
            return_value="10.0.0.1"
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_authorization_context",
            new_callable=AsyncMock,
            return_value=None  # Context not found, will raise HTTPException
        ):
            try:
                await consent_endpoint(mock_request, mock_db)
            except Exception:
                pass  # Expected to fail after rate limit check

        # Verify rate limit was called with correct parameters
        assert len(rate_limit_calls) == 1
        call = rate_limit_calls[0]
        assert call["key"] == "ratelimit:oauth:consent:ip:10.0.0.1"
        assert call["limit"] == 20  # 20/min for consent (more restrictive than authorize)
        assert call["window"] == 60
