"""
Unit tests for MCP server config invariants (Increment 49).

Tests the startup invariant: OAUTH_ISSUER_URL must start with OAUTH_ISSUER_BASE.
"""

import importlib
import os
import sys

import pytest


def reload_config_with_env(env_overrides: dict[str, str]):
    """
    Reload the config module with patched environment variables.

    Since config.py runs checks at module load time, we need to:
    1. Patch os.environ
    2. Remove the module from sys.modules (if cached)
    3. Re-import the module

    Returns the reloaded module or raises the startup error.
    """
    # Remove cached module to force fresh import
    module_name = "mcp_server.priority_guardian.config"
    if module_name in sys.modules:
        del sys.modules[module_name]

    # Save original env values
    original_env = {}
    for key in env_overrides:
        original_env[key] = os.environ.get(key)

    try:
        # Apply overrides
        for key, value in env_overrides.items():
            os.environ[key] = value

        # Import fresh (will run module-level checks)
        import mcp_server.priority_guardian.config as config_module

        return config_module
    finally:
        # Restore original env
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


class TestOAuthIssuerInvariant:
    """Tests for OAUTH_ISSUER_URL must start with OAUTH_ISSUER_BASE invariant."""

    def test_mismatched_hosts_raises_runtime_error(self):
        """
        When OAUTH_ISSUER_BASE and OAUTH_ISSUER_URL have different hosts,
        config module load should raise RuntimeError.
        """
        with pytest.raises(RuntimeError) as exc_info:
            reload_config_with_env({
                "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "PG_OAUTH_ISSUER_URL": "https://api.priority-guard.com/oauth/pg",
            })

        error_msg = str(exc_info.value)
        assert "OAUTH_ISSUER_URL must start with OAUTH_ISSUER_BASE" in error_msg
        assert "www.priority-guard.com" in error_msg
        assert "api.priority-guard.com" in error_msg
        assert "RFC 8414" in error_msg

    def test_matching_values_no_error(self):
        """
        When OAUTH_ISSUER_URL starts with OAUTH_ISSUER_BASE (same origin, different path),
        no error should be raised.
        """
        # Should not raise
        config = reload_config_with_env({
            "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
            "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
        })

        assert config.OAUTH_ISSUER_BASE == "https://www.priority-guard.com"
        assert config.OAUTH_ISSUER_URL == "https://www.priority-guard.com/oauth/pg"

    def test_url_equals_base_no_error(self):
        """
        Edge case: when OAUTH_ISSUER_URL equals OAUTH_ISSUER_BASE (no path),
        startswith is satisfied and no error should be raised.
        """
        # Should not raise
        config = reload_config_with_env({
            "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
            "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com",
        })

        assert config.OAUTH_ISSUER_BASE == "https://www.priority-guard.com"
        assert config.OAUTH_ISSUER_URL == "https://www.priority-guard.com"

    def test_localhost_default_values_no_error(self):
        """
        Default localhost values should work (both default to localhost:8000).
        This ensures dev mode still works without explicit env vars.
        """
        # Remove any overrides to use defaults
        env_keys_to_clear = ["PG_OAUTH_ISSUER_BASE", "PG_OAUTH_ISSUER_URL"]
        original_values = {k: os.environ.get(k) for k in env_keys_to_clear}

        try:
            for key in env_keys_to_clear:
                os.environ.pop(key, None)

            # Remove cached module
            module_name = "mcp_server.priority_guardian.config"
            if module_name in sys.modules:
                del sys.modules[module_name]

            # Should not raise with defaults
            import mcp_server.priority_guardian.config as config_module

            # Defaults: BASE=http://localhost:8000, URL=http://localhost:8000/oauth/pg
            assert config_module.OAUTH_ISSUER_URL.startswith(config_module.OAUTH_ISSUER_BASE)
        finally:
            # Restore original env
            for key, value in original_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
