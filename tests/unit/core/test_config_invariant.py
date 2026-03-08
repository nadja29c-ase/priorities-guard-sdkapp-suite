"""
Unit tests for backend config production URL invariants (Increment 52).

Tests the startup validators:
- OAUTH_ISSUER must use HTTPS and have no path in production
- BACKEND_PUBLIC_URL must use HTTPS in production
- PG_MCP_SERVER_URL must use HTTPS in production
"""

import os

import pytest


# Minimal required env vars for Settings instantiation
MINIMAL_ENV = {
    "DATABASE_URL": "postgresql://localhost/test",
    "ENCRYPTION_KEY": "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleTE=",
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-secret",
    "OAUTH_RSA_PRIVATE_KEY": "dGVzdA==",  # base64("test")
    "OAUTH_RSA_PUBLIC_KEY": "dGVzdA==",
    "INTERNAL_API_SECRET": "test-internal-secret",
}


def create_settings_with_env(env_overrides: dict[str, str]):
    """
    Create a fresh Settings instance with the given environment overrides.

    Pydantic Settings reads from os.environ at instantiation time,
    so we patch environ and create a new instance.
    """
    # Build complete env
    test_env = {**MINIMAL_ENV, **env_overrides}

    # Save original values
    original_env = {}
    for key in test_env:
        original_env[key] = os.environ.get(key)

    try:
        # Apply test env
        for key, value in test_env.items():
            os.environ[key] = value

        # Import fresh - Settings is instantiated at module load
        # We need to create a new instance directly
        from backend.core.config import Settings
        return Settings()
    finally:
        # Restore original env
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


class TestProductionUrlValidation:
    """Tests for production URL validation in backend config."""

    def test_oauth_issuer_with_path_raises_in_production(self):
        """
        OAUTH_ISSUER with path suffix raises ValueError in production.
        B2-2 requires issuer to be root domain only.
        """
        with pytest.raises(ValueError) as exc_info:
            create_settings_with_env({
                "ENV": "production",
                "OAUTH_ISSUER": "https://www.priority-guard.com/oauth/pg",
                "BACKEND_PUBLIC_URL": "https://www.priority-guard.com",
                "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
            })

        error_msg = str(exc_info.value)
        assert "OAUTH_ISSUER" in error_msg
        assert "path" in error_msg.lower()
        assert "/oauth/pg" in error_msg

    def test_oauth_issuer_with_http_raises_in_production(self):
        """
        OAUTH_ISSUER with HTTP scheme raises ValueError in production.
        """
        with pytest.raises(ValueError) as exc_info:
            create_settings_with_env({
                "ENV": "production",
                "OAUTH_ISSUER": "http://www.priority-guard.com",
                "BACKEND_PUBLIC_URL": "https://www.priority-guard.com",
                "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
            })

        error_msg = str(exc_info.value)
        assert "OAUTH_ISSUER" in error_msg
        assert "HTTPS" in error_msg

    def test_oauth_issuer_valid_root_https_passes_in_production(self):
        """
        OAUTH_ISSUER with valid root HTTPS domain passes in production.
        """
        # Should not raise
        settings = create_settings_with_env({
            "ENV": "production",
            "OAUTH_ISSUER": "https://www.priority-guard.com",
            "BACKEND_PUBLIC_URL": "https://www.priority-guard.com",
            "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
        })

        assert settings.OAUTH_ISSUER == "https://www.priority-guard.com"

    def test_oauth_issuer_with_trailing_slash_passes_in_production(self):
        """
        OAUTH_ISSUER with trailing slash (path="/") passes in production.
        """
        # Should not raise - "/" is acceptable
        settings = create_settings_with_env({
            "ENV": "production",
            "OAUTH_ISSUER": "https://www.priority-guard.com/",
            "BACKEND_PUBLIC_URL": "https://www.priority-guard.com",
            "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
        })

        assert settings.OAUTH_ISSUER == "https://www.priority-guard.com/"

    def test_backend_public_url_with_http_raises_in_production(self):
        """
        BACKEND_PUBLIC_URL with HTTP raises ValueError in production.
        """
        with pytest.raises(ValueError) as exc_info:
            create_settings_with_env({
                "ENV": "production",
                "OAUTH_ISSUER": "https://www.priority-guard.com",
                "BACKEND_PUBLIC_URL": "http://www.priority-guard.com",
                "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
            })

        error_msg = str(exc_info.value)
        assert "BACKEND_PUBLIC_URL" in error_msg
        assert "HTTPS" in error_msg

    def test_pg_mcp_server_url_with_http_raises_in_production(self):
        """
        PG_MCP_SERVER_URL with HTTP raises ValueError in production.
        """
        with pytest.raises(ValueError) as exc_info:
            create_settings_with_env({
                "ENV": "production",
                "OAUTH_ISSUER": "https://www.priority-guard.com",
                "BACKEND_PUBLIC_URL": "https://www.priority-guard.com",
                "PG_MCP_SERVER_URL": "http://pg.priority-guard.com",
            })

        error_msg = str(exc_info.value)
        assert "PG_MCP_SERVER_URL" in error_msg
        assert "HTTPS" in error_msg

    def test_all_checks_skipped_in_dev(self):
        """
        All production URL checks are skipped in ENV=dev.
        HTTP localhost values should work fine.
        """
        # Should not raise - dev mode skips all URL checks
        settings = create_settings_with_env({
            "ENV": "dev",
            "OAUTH_ISSUER": "http://localhost:8000",
            "BACKEND_PUBLIC_URL": "http://localhost:8000",
            "PG_MCP_SERVER_URL": "http://localhost:8003",
            "INTERNAL_API_SECRET": "",  # Also allowed empty in dev
        })

        assert settings.OAUTH_ISSUER == "http://localhost:8000"
        assert settings.BACKEND_PUBLIC_URL == "http://localhost:8000"
        assert settings.PG_MCP_SERVER_URL == "http://localhost:8003"
