"""
Unit tests for _normalize_redirect_uri localhost port handling.

Tests verify that localhost URLs with ports are correctly allowed and
preserved, while non-localhost HTTP URLs are rejected.

Gap #11: _normalize_redirect_uri Localhost Port Handling
"""

import pytest

from backend.core.oauth_provider.authorize import _normalize_redirect_uri


class TestNormalizeRedirectUri:
    """Tests for redirect_uri normalization and validation."""

    def test_localhost_with_port_allowed(self):
        """Localhost with port is allowed and port is preserved."""
        result = _normalize_redirect_uri("http://localhost:3000/callback")

        # HTTP allowed for localhost, port preserved
        assert result is not None
        assert result == "http://localhost:3000/callback"

    def test_localhost_without_port_allowed(self):
        """Localhost without port is allowed."""
        result = _normalize_redirect_uri("http://localhost/callback")

        assert result is not None
        assert result == "http://localhost/callback"

    def test_127_0_0_1_with_port_allowed(self):
        """127.0.0.1 with port is allowed and port is preserved."""
        result = _normalize_redirect_uri("http://127.0.0.1:5173/callback")

        # HTTP allowed for 127.0.0.1, port preserved
        assert result is not None
        assert result == "http://127.0.0.1:5173/callback"

    def test_non_localhost_http_rejected(self):
        """Non-localhost HTTP URLs are rejected."""
        result = _normalize_redirect_uri("http://example.com/callback")

        # HTTP not allowed for non-localhost
        assert result is None

    def test_query_rejected(self):
        """URLs with query parameters are rejected."""
        result = _normalize_redirect_uri("https://example.com/callback?foo=bar")

        # Query parameters not allowed (OAuth 2.1 strict)
        assert result is None

    def test_fragment_rejected(self):
        """URLs with fragments are rejected."""
        result = _normalize_redirect_uri("https://example.com/callback#frag")

        # Fragments not allowed (OAuth 2.1 strict)
        assert result is None

    def test_https_non_localhost_allowed(self):
        """HTTPS URLs for non-localhost are allowed."""
        result = _normalize_redirect_uri("https://example.com/callback")

        assert result == "https://example.com/callback"

    def test_https_non_localhost_with_port_allowed(self):
        """HTTPS URLs with port for non-localhost are allowed."""
        result = _normalize_redirect_uri("https://example.com:8443/callback")

        assert result == "https://example.com:8443/callback"

    def test_empty_uri_rejected(self):
        """Empty URI is rejected."""
        result = _normalize_redirect_uri("")
        assert result is None

    def test_relative_uri_rejected(self):
        """Relative URIs are rejected."""
        result = _normalize_redirect_uri("/callback")
        assert result is None


class TestRedirectUriAllowlist:
    """Tests for redirect_uri allowlist validation."""

    def test_claude_callback_uri_accepted(self):
        """Claude callback URI is accepted by the production allowlist."""
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris
        from backend.core.config import Settings

        # Use the production allowlist from Settings class
        allowed = list(Settings._CHATGPT_REDIRECT_URIS)

        valid, error = validate_redirect_uris(
            ["https://claude.ai/api/mcp/auth_callback"],
            allowed_uris=allowed
        )
        assert valid is True, f"Claude URI should be accepted: {error}"

    def test_chatgpt_uris_still_accepted(self):
        """All existing ChatGPT URIs still pass (regression guard)."""
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris
        from backend.core.config import Settings

        allowed = list(Settings._CHATGPT_REDIRECT_URIS)

        # Test all three original ChatGPT URIs
        chatgpt_uris = [
            "https://chatgpt.com/connector/oauth/ABC123",  # prefix match
            "https://chatgpt.com/connector_platform_oauth_redirect",  # exact
            "https://platform.openai.com/apps-manage/oauth",  # exact
        ]

        for uri in chatgpt_uris:
            valid, error = validate_redirect_uris([uri], allowed_uris=allowed)
            assert valid is True, f"ChatGPT URI should be accepted: {uri} - {error}"
