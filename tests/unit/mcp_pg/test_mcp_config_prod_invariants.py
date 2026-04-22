"""
Unit tests for MCP PG config production URL invariants.

Verifies that setting ENV=production with localhost/http URLs fails loudly
at config import time.
"""

import importlib
import sys
import pytest


def _reimport_config_with_env(monkeypatch, env_vars: dict):
    """Reimport the config module with specified env vars set."""
    # Remove the module from sys.modules so reimport re-runs top-level code
    sys.modules.pop("mcp_server.priority_guardian.config", None)
    for key, value in env_vars.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return importlib.import_module("mcp_server.priority_guardian.config")


def test_prod_rejects_localhost_jwks_url(monkeypatch):
    """Production import fails if PG_JWKS_URL contains localhost."""
    with pytest.raises(RuntimeError, match="Production URL validation failed"):
        _reimport_config_with_env(monkeypatch, {
            "ENV": "production",
            "INTERNAL_API_SECRET": "test-secret",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
            "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
            "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
            "PG_MCP_RESOURCE_URL": "https://pg.priority-guard.com/mcp",
            "PG_BACKEND_URL": "https://www.priority-guard.com",
            "PG_ISSUER": "https://www.priority-guard.com",
            "PG_AUDIENCE": "https://www.priority-guard.com",
            # This is the bad one:
            "PG_JWKS_URL": "http://localhost:8000/oauth/pg/jwks",
        })


def test_prod_rejects_http_backend_url(monkeypatch):
    """Production import fails if PG_BACKEND_URL uses http:// instead of https://."""
    with pytest.raises(RuntimeError, match="Production URL validation failed"):
        _reimport_config_with_env(monkeypatch, {
            "ENV": "production",
            "INTERNAL_API_SECRET": "test-secret",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
            "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
            "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
            "PG_MCP_RESOURCE_URL": "https://pg.priority-guard.com/mcp",
            "PG_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
            "PG_ISSUER": "https://www.priority-guard.com",
            "PG_AUDIENCE": "https://www.priority-guard.com",
            # This is the bad one:
            "PG_BACKEND_URL": "http://www.priority-guard.com",
        })


def test_prod_accepts_all_https_urls(monkeypatch):
    """Production import succeeds when all URL env vars are proper https:// values."""
    # Should not raise
    config = _reimport_config_with_env(monkeypatch, {
        "ENV": "production",
        "INTERNAL_API_SECRET": "test-secret",
        "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
        "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
        "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
        "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
        "PG_MCP_RESOURCE_URL": "https://pg.priority-guard.com/mcp",
        "PG_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
        "PG_BACKEND_URL": "https://www.priority-guard.com",
        "PG_ISSUER": "https://www.priority-guard.com",
        "PG_AUDIENCE": "https://www.priority-guard.com",
    })
    assert config.ENV == "production"


def test_dev_allows_localhost_urls(monkeypatch):
    """Dev env allows localhost URLs without failing."""
    # Should not raise
    config = _reimport_config_with_env(monkeypatch, {
        "ENV": "dev",
        # No URL vars set — uses localhost defaults
    })
    assert config.ENV == "dev"
    assert "localhost" in config.PG_JWKS_URL
