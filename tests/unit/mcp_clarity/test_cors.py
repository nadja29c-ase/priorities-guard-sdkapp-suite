"""
Unit tests for Clarity CORS configuration.

Tests verify:
- CORS origins are properly configured
- Wildcard is never allowed
- Production requires explicit configuration
- Dev mode has sensible defaults
"""

import importlib
import os
import pytest
from unittest.mock import patch


class TestCORSConfiguration:
    """Tests for CORS configuration in config.py."""

    def test_cors_origins_default_in_dev(self):
        """Dev mode should use default ChatGPT domains."""
        env_vars = {
            "ENV": "dev",
            "CORS_ALLOWED_ORIGINS": None,  # Not set
        }

        # Patch environment and reload config
        with patch.dict(os.environ, {k: v for k, v in env_vars.items() if v is not None}, clear=False):
            # Remove CORS_ALLOWED_ORIGINS if it exists
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            # Import fresh to get new config values
            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            # Should have default ChatGPT domains
            assert "https://chatgpt.com" in config_module.CORS_ALLOWED_ORIGINS
            assert "https://chat.openai.com" in config_module.CORS_ALLOWED_ORIGINS
            assert "https://web-sandbox.oaiusercontent.com" in config_module.CORS_ALLOWED_ORIGINS

    def test_cors_origins_no_wildcard(self):
        """Wildcard '*' must never appear in allowed origins."""
        env_vars = {
            "ENV": "dev",
            "CORS_ALLOWED_ORIGINS": None,
        }

        with patch.dict(os.environ, {k: v for k, v in env_vars.items() if v is not None}, clear=False):
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            # Wildcard must never be present
            assert "*" not in config_module.CORS_ALLOWED_ORIGINS
            assert "https://*" not in config_module.CORS_ALLOWED_ORIGINS

    def test_cors_origins_from_env(self):
        """CORS_ALLOWED_ORIGINS env var should be respected."""
        custom_origins = "https://custom.example.com,https://another.example.com"
        env_vars = {
            "ENV": "dev",
            "CORS_ALLOWED_ORIGINS": custom_origins,
        }

        with patch.dict(os.environ, env_vars, clear=False):
            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            # Should use custom origins
            assert "https://custom.example.com" in config_module.CORS_ALLOWED_ORIGINS
            assert "https://another.example.com" in config_module.CORS_ALLOWED_ORIGINS
            # Should NOT have defaults when custom is set
            # (Actually defaults might still be there if parsing is additive - let's check length)
            assert len(config_module.CORS_ALLOWED_ORIGINS) == 2

    def test_cors_origins_from_env_strips_whitespace(self):
        """Origins with whitespace should be trimmed."""
        custom_origins = "  https://custom.example.com  , https://another.example.com  "
        env_vars = {
            "ENV": "dev",
            "CORS_ALLOWED_ORIGINS": custom_origins,
        }

        with patch.dict(os.environ, env_vars, clear=False):
            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            # Whitespace should be stripped
            assert "https://custom.example.com" in config_module.CORS_ALLOWED_ORIGINS
            assert "https://another.example.com" in config_module.CORS_ALLOWED_ORIGINS
            # No whitespace in origins
            for origin in config_module.CORS_ALLOWED_ORIGINS:
                assert origin == origin.strip()

    def test_production_requires_explicit_config(self):
        """Production without CORS_ALLOWED_ORIGINS should raise RuntimeError."""
        env_vars = {
            "ENV": "production",
            # CHATGPT_CLIENT_ID_CLARITY is also required in production
            "CHATGPT_CLIENT_ID_CLARITY": "test-client-id",
            # Other required production env vars (to reach the CORS guard)
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
            "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            # Remove CORS_ALLOWED_ORIGINS if it exists
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            import mcp_server.clarity.config as config_module

            with pytest.raises(RuntimeError) as exc_info:
                importlib.reload(config_module)

            assert "CORS_ALLOWED_ORIGINS" in str(exc_info.value)
            assert "production" in str(exc_info.value).lower()

    def test_staging_requires_explicit_config(self):
        """Staging without CORS_ALLOWED_ORIGINS should raise RuntimeError."""
        env_vars = {
            "ENV": "staging",
            # CHATGPT_CLIENT_ID_CLARITY is also required in staging
            "CHATGPT_CLIENT_ID_CLARITY": "test-client-id",
            # Other required production env vars (to reach the CORS guard)
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
            "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            import mcp_server.clarity.config as config_module

            with pytest.raises(RuntimeError) as exc_info:
                importlib.reload(config_module)

            assert "CORS_ALLOWED_ORIGINS" in str(exc_info.value)

    def test_production_accepts_explicit_config(self):
        """Production with explicit CORS_ALLOWED_ORIGINS should not raise."""
        env_vars = {
            "ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com,https://web-sandbox.oaiusercontent.com",
            # CHATGPT_CLIENT_ID_CLARITY is also required in production
            "CHATGPT_CLIENT_ID_CLARITY": "test-client-id",
            # Other required production env vars
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
            "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            import mcp_server.clarity.config as config_module

            # Should not raise
            importlib.reload(config_module)

            # Should use the explicit config
            assert "https://chatgpt.com" in config_module.CORS_ALLOWED_ORIGINS
            assert "https://web-sandbox.oaiusercontent.com" in config_module.CORS_ALLOWED_ORIGINS

    def test_is_dev_true_for_dev_env(self):
        """IS_DEV should be True for dev environment."""
        env_vars = {"ENV": "dev"}

        with patch.dict(os.environ, env_vars, clear=False):
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            assert config_module.IS_DEV is True

    def test_is_dev_true_for_development_env(self):
        """IS_DEV should be True for development environment."""
        env_vars = {"ENV": "development"}

        with patch.dict(os.environ, env_vars, clear=False):
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            assert config_module.IS_DEV is True

    def test_is_dev_true_for_local_env(self):
        """IS_DEV should be True for local environment."""
        env_vars = {"ENV": "local"}

        with patch.dict(os.environ, env_vars, clear=False):
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            assert config_module.IS_DEV is True

    def test_is_dev_false_for_production(self):
        """IS_DEV should be False for production environment."""
        env_vars = {
            "ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            # CHATGPT_CLIENT_ID_CLARITY is also required in production
            "CHATGPT_CLIENT_ID_CLARITY": "test-client-id",
            # Other required production env vars
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
            "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            assert config_module.IS_DEV is False

    def test_empty_cors_origins_filtered(self):
        """Empty origins in comma-separated list should be filtered out."""
        env_vars = {
            "ENV": "dev",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com,,https://chat.openai.com,",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            # Should only have non-empty origins
            assert "" not in config_module.CORS_ALLOWED_ORIGINS
            assert len(config_module.CORS_ALLOWED_ORIGINS) == 2


class TestCORSMiddlewareConfiguration:
    """Tests for CORS middleware in server.py (smoke tests)."""

    def test_server_imports_cors_config(self):
        """Server should import CORS configuration from config module."""
        # Reset to dev mode first
        env_vars = {"ENV": "dev"}
        with patch.dict(os.environ, env_vars, clear=False):
            if "CORS_ALLOWED_ORIGINS" in os.environ:
                del os.environ["CORS_ALLOWED_ORIGINS"]

            import mcp_server.clarity.config as config_module
            importlib.reload(config_module)

            # Now import server
            from mcp_server.clarity import server

            # Server should have access to CORS config
            from mcp_server.clarity.config import CORS_ALLOWED_ORIGINS, IS_DEV

            assert CORS_ALLOWED_ORIGINS is not None
            assert isinstance(CORS_ALLOWED_ORIGINS, list)
            assert len(CORS_ALLOWED_ORIGINS) > 0
