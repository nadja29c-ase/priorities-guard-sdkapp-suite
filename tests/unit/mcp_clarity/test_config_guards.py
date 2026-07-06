"""
Unit tests for Clarity config production guards.

Verifies that:
- CLARITY_BACKEND_URL localhost rejection works correctly (2026-07-05 incident)
- CLARITY_OAUTH_ISSUER_URL exact-value assertion works correctly (inc_94)
- CLARITY_JWKS_URL exact-value assertion works correctly (inc_95)

Uses subprocess reimport pattern to test config-time guards that raise
RuntimeError during module import.
"""

import importlib
import sys
import pytest


# All Clarity config env vars that affect guards/behavior.
# The helper clears these before each test to ensure hermetic testing.
# inc_95 hardening: prevents ambient shell env from invalidating test premises.
_CLARITY_CONFIG_ENV_VARS = [
    "ENV",
    "CLARITY_JWKS_URL",
    "CLARITY_BACKEND_URL",
    "CLARITY_OAUTH_ISSUER_URL",
    "CLARITY_ISSUER",
    "CLARITY_AUDIENCE",
    "CLARITY_MCP_SERVER_URL",
    "CLARITY_MCP_RESOURCE_URL",
    "CORS_ALLOWED_ORIGINS",
    "INTERNAL_API_SECRET",
]


def _reimport_config_with_env(monkeypatch, env_vars: dict):
    """Reimport the config module with specified env vars set.

    Clears all known Clarity config env vars first, then applies the
    specified values. This ensures tests are hermetic and don't depend
    on ambient shell environment (inc_95 hardening per Codex review).
    """
    # Remove the module from sys.modules so reimport re-runs top-level code
    sys.modules.pop("mcp_server.clarity.config", None)

    # Clear all known config vars first to ensure hermetic test
    for key in _CLARITY_CONFIG_ENV_VARS:
        monkeypatch.delenv(key, raising=False)

    # Apply test-specific env vars
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
                # Set JWKS to valid value to reach BACKEND_URL guard
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
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
                # Set JWKS to valid value to reach BACKEND_URL guard
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
                # CLARITY_BACKEND_URL not set -> falls to localhost default
            })

    def test_staging_rejects_localhost_backend_url(self, monkeypatch):
        """Staging environment also rejects localhost CLARITY_BACKEND_URL."""
        with pytest.raises(RuntimeError, match="CLARITY_BACKEND_URL contains 'localhost'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "staging",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                # Set JWKS to valid value to reach BACKEND_URL guard
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
                # CLARITY_BACKEND_URL not set -> falls to localhost default
            })

    def test_prod_accepts_https_backend_url(self, monkeypatch):
        """Production import succeeds with proper https:// CLARITY_BACKEND_URL."""
        # Should not raise
        config = _reimport_config_with_env(monkeypatch, {
            "ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
            "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
            "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
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


class TestUnknownEnvGuard:
    """Tests for unknown ENV fail-fast guard.

    Prevents typos like ENV=produciton from silently disabling production guards.
    """

    def test_unknown_env_raises_runtime_error(self, monkeypatch):
        """Unknown ENV value fails at import with clear error message."""
        with pytest.raises(RuntimeError, match="Unknown ENV value 'produciton'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "produciton",  # Typo
            })

    def test_case_sensitive_env_fails(self, monkeypatch):
        """ENV values are case-sensitive — Production != production."""
        with pytest.raises(RuntimeError, match="Unknown ENV value 'Production'"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "Production",  # Wrong case
            })

    def test_all_known_dev_values_accepted(self, monkeypatch):
        """All known dev ENV values import cleanly."""
        for env_val in ("dev", "development", "local", "test", "ci"):
            config = _reimport_config_with_env(monkeypatch, {"ENV": env_val})
            assert config.ENV == env_val
            assert config.IS_DEV is True

    def test_all_known_production_values_accepted(self, monkeypatch):
        """All known production ENV values import cleanly (with required env vars)."""
        for env_val in ("production", "prod", "staging"):
            config = _reimport_config_with_env(monkeypatch, {
                "ENV": env_val,
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
            })
            assert config.ENV == env_val
            assert config.IS_DEV is False


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

        # Need to set production env vars for production to work
        config_prod = _reimport_config_with_env(monkeypatch, {
            "ENV": "production",
            "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
            "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
            "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
            "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
        })
        assert config_prod.IS_DEV is False


class TestOAuthIssuerUrlGuard:
    """Tests for CLARITY_OAUTH_ISSUER_URL exact-value assertion in production.

    inc_94: Guard is assert-known-good (exact match), not blocklist.
    Expected production value: https://www.priority-guard.com/oauth/mindsort
    (ADR_005 Shape #2 for MindSort-OpenAI).

    For each test, we document what bug would still pass it — this proves
    the test is assert-known-good, not blocklist.
    """

    # The expected production value per ADR_005 Shape #2
    EXPECTED_ISSUER = "https://www.priority-guard.com/oauth/mindsort"

    # Base production env vars (all required guards satisfied)
    # inc_95: CLARITY_JWKS_URL added to pass JWKS guard (fires before OAUTH_ISSUER_URL guard)
    _PROD_BASE = {
        "ENV": "production",
        "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
        "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
        "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
    }

    def test_prod_rejects_localhost_default(self, monkeypatch):
        """Production rejects localhost dev-default OAUTH_ISSUER_URL.

        Bug this test catches: env var not set, falls to localhost default.
        Bug that would still pass: any non-localhost wrong value.
        """
        with pytest.raises(RuntimeError, match="CLARITY_OAUTH_ISSUER_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                # CLARITY_OAUTH_ISSUER_URL not set -> falls to localhost default
            })

    def test_prod_rejects_oauth_pg_path(self, monkeypatch):
        """Production rejects /oauth/pg path (Shape #3, wrong for Clarity).

        Bug this test catches: using PG's OAuth path instead of MindSort's.
        Bug that would still pass: any other non-expected path.
        """
        with pytest.raises(RuntimeError, match="CLARITY_OAUTH_ISSUER_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
            })

    def test_prod_rejects_bare_domain(self, monkeypatch):
        """Production rejects bare domain without path (Shape #3 issuer).

        Bug this test catches: using AS issuer as OAUTH_ISSUER_URL.
        Bug that would still pass: any path-qualified wrong value.
        """
        with pytest.raises(RuntimeError, match="CLARITY_OAUTH_ISSUER_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com",
            })

    def test_prod_rejects_arbitrary_wrong_value(self, monkeypatch):
        """Production rejects any arbitrary wrong value (proves assert-known-good).

        Bug this test catches: any value that's not the expected one.
        Bug that would still pass: NONE — this proves the guard is exact-match,
        not a blocklist of known-bad values.
        """
        with pytest.raises(RuntimeError, match="CLARITY_OAUTH_ISSUER_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_OAUTH_ISSUER_URL": "https://example.com/oauth/whatever",
            })

    def test_prod_rejects_trailing_slash_variant(self, monkeypatch):
        """Production rejects trailing-slash variant (exact match required).

        Bug this test catches: trailing slash typo in env var.
        Bug that would still pass: any other typo/variant.
        """
        with pytest.raises(RuntimeError, match="CLARITY_OAUTH_ISSUER_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort/",
            })

    def test_prod_accepts_exact_expected_value(self, monkeypatch):
        """Production accepts the exact expected OAUTH_ISSUER_URL."""
        config = _reimport_config_with_env(monkeypatch, {
            **self._PROD_BASE,
            "CLARITY_OAUTH_ISSUER_URL": self.EXPECTED_ISSUER,
        })
        assert config.OAUTH_ISSUER_URL == self.EXPECTED_ISSUER

    def test_staging_also_enforces_guard(self, monkeypatch):
        """Staging environment also enforces the OAUTH_ISSUER_URL guard."""
        with pytest.raises(RuntimeError, match="CLARITY_OAUTH_ISSUER_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "staging",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
            })

    def test_prod_alias_also_enforces_guard(self, monkeypatch):
        """ENV=prod (alias) also enforces the OAUTH_ISSUER_URL guard."""
        with pytest.raises(RuntimeError, match="CLARITY_OAUTH_ISSUER_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "prod",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks",
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
            })

    def test_dev_allows_oauth_pg_default(self, monkeypatch):
        """Dev environment allows /oauth/pg default without failing.

        This is critical: dev legitimately uses /oauth/pg (shared backend
        discovery) for local testing. The guard must NOT fire in dev.
        """
        config = _reimport_config_with_env(monkeypatch, {
            "ENV": "dev",
            # No CLARITY_OAUTH_ISSUER_URL set — uses /oauth/pg default
        })
        assert config.ENV == "dev"
        assert "/oauth/pg" in config.OAUTH_ISSUER_URL

    def test_test_env_allows_any_value(self, monkeypatch):
        """Test environment allows any OAUTH_ISSUER_URL without failing."""
        config = _reimport_config_with_env(monkeypatch, {
            "ENV": "test",
            "CLARITY_OAUTH_ISSUER_URL": "https://example.com/anything",
        })
        assert config.OAUTH_ISSUER_URL == "https://example.com/anything"


class TestJwksUrlGuard:
    """Tests for CLARITY_JWKS_URL exact-value assertion in production.

    inc_95: Guard is assert-known-good (exact match), not blocklist.
    Expected production value: https://www.priority-guard.com/oauth/mindsort/jwks
    (ADR_005 Shape #2 for MindSort-OpenAI).

    JWKS URL is the JWT trust anchor — if wrong in production:
    - localhost default → can't fetch keys → auth fails closed (full outage)
    - wrong production URL → validates against wrong key set → security issue

    For each test, we document what bug would still pass it — this proves
    the test is assert-known-good, not blocklist.
    """

    # The expected production value per ADR_005 Shape #2
    EXPECTED_JWKS_URL = "https://www.priority-guard.com/oauth/mindsort/jwks"

    # Base production env vars (all required guards satisfied)
    _PROD_BASE = {
        "ENV": "production",
        "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
        "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
        "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
    }

    def test_prod_rejects_localhost_default(self, monkeypatch):
        """Production rejects localhost dev-default CLARITY_JWKS_URL.

        Bug this test catches: env var not set, falls to localhost default.
        Bug that would still pass: any non-localhost wrong value.
        """
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                # CLARITY_JWKS_URL not set -> falls to localhost default
            })

    def test_prod_rejects_oauth_pg_path(self, monkeypatch):
        """Production rejects /oauth/pg/jwks path (wrong for Clarity).

        Bug this test catches: using PG's JWKS path instead of MindSort's.
        Bug that would still pass: any other non-expected path.
        """
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
            })

    def test_prod_rejects_bare_domain(self, monkeypatch):
        """Production rejects bare domain without path.

        Bug this test catches: JWKS URL missing the path entirely.
        Bug that would still pass: any path-qualified wrong value.
        """
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/jwks",
            })

    def test_prod_rejects_arbitrary_wrong_value(self, monkeypatch):
        """Production rejects any arbitrary wrong value (proves assert-known-good).

        Bug this test catches: any value that's not the expected one.
        Bug that would still pass: NONE — this proves the guard is exact-match,
        not a blocklist of known-bad values.
        """
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_JWKS_URL": "https://example.com/.well-known/jwks.json",
            })

    def test_prod_rejects_trailing_slash_variant(self, monkeypatch):
        """Production rejects trailing-slash variant (exact match required).

        Bug this test catches: trailing slash typo in env var.
        Bug that would still pass: any other typo/variant.
        """
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/mindsort/jwks/",
            })

    def test_prod_rejects_http_instead_of_https(self, monkeypatch):
        """Production rejects http:// (must be https://).

        Bug this test catches: http scheme typo.
        Bug that would still pass: any other scheme/domain issue.
        """
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                **self._PROD_BASE,
                "CLARITY_JWKS_URL": "http://www.priority-guard.com/oauth/mindsort/jwks",
            })

    def test_prod_accepts_exact_expected_value(self, monkeypatch):
        """Production accepts the exact expected CLARITY_JWKS_URL."""
        config = _reimport_config_with_env(monkeypatch, {
            **self._PROD_BASE,
            "CLARITY_JWKS_URL": self.EXPECTED_JWKS_URL,
        })
        assert config.CLARITY_JWKS_URL == self.EXPECTED_JWKS_URL

    def test_staging_also_enforces_guard(self, monkeypatch):
        """Staging environment also enforces the CLARITY_JWKS_URL guard."""
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "staging",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
            })

    def test_prod_alias_also_enforces_guard(self, monkeypatch):
        """ENV=prod (alias) also enforces the CLARITY_JWKS_URL guard."""
        with pytest.raises(RuntimeError, match="CLARITY_JWKS_URL must be"):
            _reimport_config_with_env(monkeypatch, {
                "ENV": "prod",
                "CORS_ALLOWED_ORIGINS": "https://chatgpt.com",
                "CLARITY_BACKEND_URL": "https://www.priority-guard.com",
                "CLARITY_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/mindsort",
                "CLARITY_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
            })

    def test_dev_allows_localhost_default(self, monkeypatch):
        """Dev environment allows localhost JWKS URL without failing.

        This is critical: dev legitimately uses localhost defaults for local
        testing. The guard must NOT fire in dev.
        """
        config = _reimport_config_with_env(monkeypatch, {
            "ENV": "dev",
            # No CLARITY_JWKS_URL set — uses localhost default
        })
        assert config.ENV == "dev"
        assert "localhost" in config.CLARITY_JWKS_URL

    def test_test_env_allows_any_value(self, monkeypatch):
        """Test environment allows any CLARITY_JWKS_URL without failing."""
        config = _reimport_config_with_env(monkeypatch, {
            "ENV": "test",
            "CLARITY_JWKS_URL": "https://example.com/any/jwks",
        })
        assert config.CLARITY_JWKS_URL == "https://example.com/any/jwks"


class TestOAuthConfigLogging:
    """Tests for startup logging of resolved OAuth config.

    inc_94: Ensures resolved OAuth URLs are logged at import time
    to eliminate dashboard-vs-runtime ambiguity.
    """

    def test_logging_emits_resolved_urls(self, monkeypatch, capsys):
        """Startup logging emits resolved OAuth URLs with actual values.

        Structlog logs to stdout, so we capture stdout instead of using caplog.
        inc_95: Extended to include jwks_url and assert resolved VALUES appear,
        not just field names (per Codex review — proves the log is actionable).
        """
        config = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})

        captured = capsys.readouterr()
        # Check that the log entry exists
        assert "clarity.config.oauth_resolved" in captured.out, \
            f"Expected oauth_resolved log entry not found in stdout: {captured.out}"

        # Check field names appear (basic structure check)
        assert "oauth_issuer_url" in captured.out
        assert "jwks_url" in captured.out
        assert "mcp_server_url" in captured.out
        assert "mcp_resource_url" in captured.out

        # inc_95 hardening: assert resolved VALUES appear, not just field names.
        # This proves the log is actionable for debugging — you can see the
        # actual runtime value, not just "oauth_issuer_url=<something>".
        assert config.OAUTH_ISSUER_URL in captured.out, \
            f"Expected OAUTH_ISSUER_URL value {config.OAUTH_ISSUER_URL!r} in log"
        assert config.CLARITY_JWKS_URL in captured.out, \
            f"Expected CLARITY_JWKS_URL value {config.CLARITY_JWKS_URL!r} in log"
        assert config.MCP_SERVER_URL in captured.out, \
            f"Expected MCP_SERVER_URL value {config.MCP_SERVER_URL!r} in log"
        assert config.MCP_RESOURCE_URL in captured.out, \
            f"Expected MCP_RESOURCE_URL value {config.MCP_RESOURCE_URL!r} in log"

    def test_logged_urls_are_non_secret(self, monkeypatch):
        """Logged URLs contain no secrets or PII.

        The logged values (OAUTH_ISSUER_URL, CLARITY_JWKS_URL, MCP_SERVER_URL,
        MCP_RESOURCE_URL) are public discovery endpoint URLs, not secrets.
        inc_95: Extended to include CLARITY_JWKS_URL.
        """
        config = _reimport_config_with_env(monkeypatch, {"ENV": "dev"})

        # These are public URLs, not secrets
        assert "localhost" in config.OAUTH_ISSUER_URL or "priority-guard" in config.OAUTH_ISSUER_URL
        assert "localhost" in config.CLARITY_JWKS_URL or "priority-guard" in config.CLARITY_JWKS_URL
        assert "localhost" in config.MCP_SERVER_URL or "priority-guard" in config.MCP_SERVER_URL
        assert "localhost" in config.MCP_RESOURCE_URL or "priority-guard" in config.MCP_RESOURCE_URL

        # None of these should contain secret patterns
        for url in [config.OAUTH_ISSUER_URL, config.CLARITY_JWKS_URL, config.MCP_SERVER_URL, config.MCP_RESOURCE_URL]:
            assert "password" not in url.lower()
            assert "secret" not in url.lower()
            assert "token" not in url.lower()
            assert "key=" not in url.lower()
