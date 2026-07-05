"""
Unit tests for Clarity config production guards.

Verifies that CLARITY_BACKEND_URL localhost rejection works correctly
in production environments. These guards were added after the 2026-07-05
silent persistence failure incident.

Uses subprocess reimport pattern to test config-time guards that raise
RuntimeError during module import.
"""

import importlib
import sys
import pytest


def _reimport_config_with_env(monkeypatch, env_vars: dict):
    """Reimport the config module with specified env vars set."""
    # Remove the module from sys.modules so reimport re-runs top-level code
    sys.modules.pop("mcp_server.clarity.config", None)
    for key, value in env_vars.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return importlib.import_module("mcp_server.clarity.config")


class TestBackendUrlGuard:
    """Tests for CLARITY_BACKEND_URL localhost rejection in production."""

    def test_prod_rejects_localhost_backend_url(self, monkeypatch):
        """Production import fails if CLARITY_BACKEND_URL contains localhost."""
        with pytest.raises(RuntimeError, match="CLARITY_BACKEND_URL contains 'localhost'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                # CLARITY_BACKEND_URL not set -> falls to localhost default
            })

    def test_prod_alias_rejects_localhost_backend_url(self, monkeypatch):
        """ENV=prod (alias) also rejects localhost CLARITY_BACKEND_URL.

        This was a gap in the original guard: it only checked ("production", "staging")
        but PG uses ENV=prod as an alias.
        """
        with pytest.raises(RuntimeError, match="CLARITY_BACKEND_URL contains 'localhost'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "prod",  # The alias that was missing
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                # CLARITY_BACKEND_URL not set -> falls to localhost default
            })

    def test_staging_rejects_localhost_backend_url(self, monkeypatch):
        """Staging environment also rejects localhost CLARITY_BACKEND_URL."""
        with pytest.raises(RuntimeError, match="CLARITY_BACKEND_URL contains 'localhost'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "staging",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                # CLARITY_BACKEND_URL not set -> falls to localhost default
            })

    def test_prod_accepts_https_backend_url(self, monkeypatch):
        """Production import succeeds with proper https:// CLARITY_BACKEND_URL."""
        # Should not raise
        config = _reimport_config_with_env(monkeypatch, {
            "ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
        })
        assert config.BACKEND_URL == "https://www.priority-guard.com"

    def test_dev_allows_localhost_backend_url(self, monkeypatch):
        """Dev environment allows localhost CLARITY_BACKEND_URL without failing."""
        # Should not raise
        config = _reimport_config_with_env(monkeypatch, {
            "ENV": "dev",
            # No CLARITY_BACKEND_URL set — uses localhost default
        })
        assert config.ENV == "dev"
        assert "localhost" in config.BACKEND_URL


class TestProductionPredicateParity:
    """Tests for canonical _is_production_env predicate parity."""

    def test_predicate_includes_prod_alias(self, monkeypatch):
        """_is_production_env includes 'prod' alias."""
        config = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})
        assert config._is_production_env("production") is True
        assert config._is_production_env("prod") is True
        assert config._is_production_env("staging") is True
        assert config._is_production_env("dev") is False

    def test_is_dev_inverse_of_production(self, monkeypatch):
        """IS_DEV is the inverse of _is_production_env."""
        config_dev = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})
        assert config_dev.IS_DEV is True

        # Need to set CLARITY_BACKEND_URL for production to work
        config_prod = _reimport_config_with_env(monkeypatch, {
            "ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
        })
        assert config_prod.IS_DEV is False
