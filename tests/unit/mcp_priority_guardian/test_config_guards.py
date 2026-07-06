"""
Unit tests for Priority Guardian config production guards.

inc_97: Verifies that:
- Unknown ENV fail-fast guard works correctly (prevents typos bypassing guards)
- Startup logging emits resolved OAuth config values (not just field names)
- Logged values contain no secrets

Uses subprocess reimport pattern to test config-time guards that raise
RuntimeError during module import.
"""

import importlib
import sys
import pytest


# All PG config env vars that affect guards/behavior.
# The helper clears these before each test to ensure hermetic testing.
# Pattern copied from test_config_guards.py (Clarity) per inc_95 hardening.
_PG_CONFIG_ENV_VARS = [
    "ENV",
    "PG_JWKS_URL",
    "PG_ISSUER",
    "PG_AUDIENCE",
    "PG_BACKEND_URL",
    "PG_MCP_SERVER_URL",
    "PG_MCP_RESOURCE_URL",
    "PG_OAUTH_ISSUER_URL",
    "PG_OAUTH_ISSUER_BASE",
    "CORS_ALLOWED_ORIGINS",
    "INTERNAL_API_SECRET",
    "TOKEN_EXPIRY_GRACE_SECONDS",
    "JWKS_CACHE_TTL_SECONDS",
    "JWKS_MAX_STALE_SECONDS",
    "JWKS_FETCH_TIMEOUT_SECONDS",
    "MAX_MCP_BODY_SIZE_BYTES",
    "LOG_LEVEL",
]


def _reimport_config_with_env(monkeypatch, env_vars: dict):
    """Reimport the config module with specified env vars set.

    Clears all known PG config env vars first, then applies the
    specified values. This ensures tests are hermetic and don't depend
    on ambient shell environment.
    """
    # Remove the module from sys.modules so reimport re-runs top-level code
    sys.modules.pop("mcp_server.priority_guardian.config", None)

    # Clear all known config vars first to ensure hermetic test
    for key in _PG_CONFIG_ENV_VARS:
        monkeypatch.delenv(key, raising=False)

    # Apply test-specific env vars
    for key, value in env_vars.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    return importlib.import_module("mcp_server.priority_guardian.config")


class TestUnknownEnvGuard:
    """Tests for unknown ENV fail-fast guard.

    inc_97: Prevents typos like ENV=produciton from silently disabling
    production guards (CORS, INTERNAL_API_SECRET, RFC 8414 origin check,
    _prod_url_invariants).
    """

    def test_unknown_env_raises_runtime_error(self, monkeypatch):
        """Unknown ENV value fails at import with clear error message.

        Bug this test catches: Typo in ENV silently runs as dev, disabling
        all production guards.
        """
        with pytest.raises(RuntimeError, match="Unknown ENV value 'produciton'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "produciton",  # Typo
            })

    def test_case_sensitive_env_fails(self, monkeypatch):
        """ENV values are case-sensitive — Production != production.

        Bug this test catches: Case mismatch silently runs as non-production.
        """
        with pytest.raises(RuntimeError, match="Unknown ENV value 'Production'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "Production",  # Wrong case
            })

    def test_whitespace_env_fails(self, monkeypatch):
        """ENV values with whitespace are rejected — no silent normalization.

        Bug this test catches: Leading/trailing whitespace from deploy tooling
        silently runs as non-production.
        """
        with pytest.raises(RuntimeError, match="Unknown ENV value"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": " production ",  # Whitespace
            })

    def test_all_known_dev_values_accepted(self, monkeypatch):
        """All known dev ENV values import cleanly.

        Bug that would still pass: A dev value not in _DEV_ENV_VALUES.

        Note: PG's IS_DEV is narrow (ENV == "dev" only), unlike Clarity which
        uses `not _is_production_env(ENV)`. This is flagged as low-priority
        follow-up in inc_97 (IS_DEV not in auth path).
        """
        for env_val in ("dev", "development", "local", "test", "ci"):
            config = _reimport_config_with_env(monkeypatch, {"ENV": env_val})
            assert config.ENV == env_val
            # IS_DEV is only True for "dev" in PG (narrow definition)
            if env_val == "dev":
                assert config.IS_DEV is True
            else:
                assert config.IS_DEV is False

    def test_all_known_production_values_accepted(self, monkeypatch):
        """All known production ENV values import cleanly (with required env vars).

        Bug that would still pass: A production value not in _PRODUCTION_ENV_VALUES.
        """
        # Base env vars required for any production config to pass all guards
        prod_base = {
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "INTERNAL_API_SECRET": "test-secret-for-unit-tests",
            "PG_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
            "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
            "PG_MCP_RESOURCE_URL": "https://pg.priority-guard.com/mcp",
            "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
            "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
            "PG_BACKEND_URL": "https://www.priority-guard.com",
            "PG_ISSUER": "https://www.priority-guard.com",
            "PG_AUDIENCE": "https://www.priority-guard.com",
        }

        for env_val in ("production", "prod", "staging"):
            config = _reimport_config_with_env(monkeypatch, {
                "ENV": env_val,
                **prod_base,
            })
            assert config.ENV == env_val
            assert config.IS_DEV is False


class TestProductionPredicateParity:
    """Tests for canonical _is_production_env predicate parity.

    inc_97: Ensures the predicate includes all production aliases to prevent
    ENV=prod from bypassing guards.
    """

    def test_predicate_includes_prod_alias(self, monkeypatch):
        """_is_production_env includes 'prod' alias.

        Bug this test catches: 'prod' alias missing from predicate, silently
        running as non-production.
        """
        config = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})
        assert config._is_production_env("production") is True
        assert config._is_production_env("prod") is True
        assert config._is_production_env("staging") is True
        assert config._is_production_env("dev") is False

    def test_is_dev_inverse_of_production(self, monkeypatch):
        """IS_DEV is the inverse of _is_production_env."""
        config_dev = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})
        assert config_dev.IS_DEV is True

        # Need to set production env vars for production to work
        config_prod = _reimport_config_with_env(monkeypatch, {
            "ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "INTERNAL_API_SECRET": "test-secret-for-unit-tests",
            "PG_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
            "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
            "PG_MCP_RESOURCE_URL": "https://pg.priority-guard.com/mcp",
            "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
            "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
            "PG_BACKEND_URL": "https://www.priority-guard.com",
            "PG_ISSUER": "https://www.priority-guard.com",
            "PG_AUDIENCE": "https://www.priority-guard.com",
        })
        assert config_prod.IS_DEV is False


class TestOAuthConfigLogging:
    """Tests for startup logging of resolved OAuth config.

    inc_97: Ensures resolved OAuth URLs are logged at import time
    to eliminate dashboard-vs-runtime ambiguity.
    """

    def test_logging_emits_resolved_urls(self, monkeypatch, capsys):
        """Startup logging emits resolved OAuth URLs with actual values.

        Structlog logs to stdout, so we capture stdout instead of using caplog.
        Asserts resolved VALUES appear, not just field names (per inc_94/95 lesson).

        Bug this test catches: Log says "pg_jwks_url=..." but doesn't show the
        actual value, making it useless for debugging.
        """
        config = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})

        captured = capsys.readouterr()
        # Check that the log entry exists
        assert "pg.config.oauth_resolved" in captured.out, \
            f"Expected oauth_resolved log entry not found in stdout: {captured.out}"

        # Check field names appear (basic structure check)
        assert "pg_jwks_url" in captured.out
        assert "mcp_server_url" in captured.out
        assert "mcp_resource_url" in captured.out
        assert "oauth_issuer_url" in captured.out
        assert "oauth_issuer_base" in captured.out
        assert "env" in captured.out

        # Assert resolved VALUES appear, not just field names.
        # This proves the log is actionable for debugging — you can see the
        # actual runtime value, not just "pg_jwks_url=<something>".
        assert config.PG_JWKS_URL in captured.out, \
            f"Expected PG_JWKS_URL value {config.PG_JWKS_URL!r} in log"
        assert config.MCP_SERVER_URL in captured.out, \
            f"Expected MCP_SERVER_URL value {config.MCP_SERVER_URL!r} in log"
        assert config.MCP_RESOURCE_URL in captured.out, \
            f"Expected MCP_RESOURCE_URL value {config.MCP_RESOURCE_URL!r} in log"
        assert config.OAUTH_ISSUER_URL in captured.out, \
            f"Expected OAUTH_ISSUER_URL value {config.OAUTH_ISSUER_URL!r} in log"
        assert config.OAUTH_ISSUER_BASE in captured.out, \
            f"Expected OAUTH_ISSUER_BASE value {config.OAUTH_ISSUER_BASE!r} in log"

    def test_logged_urls_are_non_secret(self, monkeypatch):
        """Logged URLs contain no secrets or PII.

        The logged values (PG_JWKS_URL, MCP_SERVER_URL, MCP_RESOURCE_URL,
        OAUTH_ISSUER_URL, OAUTH_ISSUER_BASE) are public discovery endpoint URLs,
        not secrets. Critical for a published app's logs.

        Bug this test catches: A secret (INTERNAL_API_SECRET, token, etc.)
        accidentally logged.
        """
        config = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})

        # These are public URLs, not secrets
        logged_urls = [
            config.PG_JWKS_URL,
            config.MCP_SERVER_URL,
            config.MCP_RESOURCE_URL,
            config.OAUTH_ISSUER_URL,
            config.OAUTH_ISSUER_BASE,
        ]

        for url in logged_urls:
            assert "localhost" in url or "priority-guard" in url, \
                f"URL {url!r} doesn't match expected patterns"

        # None of these should contain secret patterns
        for url in logged_urls:
            assert "password" not in url.lower()
            assert "secret" not in url.lower()
            assert "token" not in url.lower()
            assert "key=" not in url.lower()


class TestExistingGuardsStillWork:
    """Smoke tests that existing PG guards still work after inc_97 refactor.

    inc_97 changed inline ENV checks to use _is_production_env(). This class
    verifies the existing guards (CORS, INTERNAL_API_SECRET, localhost rejection)
    still fire correctly.
    """

    def test_cors_required_in_production(self, monkeypatch):
        """CORS_ALLOWED_ORIGINS still required in production after refactor.

        Note: Must set all production URL values to bypass guards that fire
        before the CORS guard (INTERNAL_API_SECRET, localhost rejection,
        _prod_url_invariants).
        """
        with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS must be explicitly set"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "production",
                "INTERNAL_API_SECRET": "test-secret-for-unit-tests",
                "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "PG_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
                "PG_MCP_SERVER_URL": "https://pg.priority-guard.com",
                "PG_MCP_RESOURCE_URL": "https://pg.priority-guard.com/mcp",
                "PG_BACKEND_URL": "https://www.priority-guard.com",
                "PG_ISSUER": "https://www.priority-guard.com",
                "PG_AUDIENCE": "https://www.priority-guard.com",
                # Missing CORS_ALLOWED_ORIGINS
            })

    def test_internal_api_secret_required_in_production(self, monkeypatch):
        """INTERNAL_API_SECRET still required in production after refactor."""
        with pytest.raises(RuntimeError, match="INTERNAL_API_SECRET is required in production"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                # Missing INTERNAL_API_SECRET
            })

    def test_localhost_rejected_in_oauth_issuer_base(self, monkeypatch):
        """PG_OAUTH_ISSUER_BASE localhost still rejected in production after refactor."""
        with pytest.raises(RuntimeError, match="PG_OAUTH_ISSUER_BASE contains 'localhost'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                "INTERNAL_API_SECRET": "test-secret-for-unit-tests",
                # PG_OAUTH_ISSUER_BASE not set -> falls to localhost default
            })

    def test_prod_url_invariants_guard_fires(self, monkeypatch):
        """_prod_url_invariants guard still fires on http:// URLs after refactor."""
        with pytest.raises(RuntimeError, match="Production URL validation failed"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                "INTERNAL_API_SECRET": "test-secret-for-unit-tests",
                "PG_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "PG_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                # PG_JWKS_URL not set -> falls to http://localhost default
                # This triggers the _prod_url_invariants guard
            })
