"""
MindSort Claude MCP Server discovery tests (inc_05 + inc_05b).

Tests OAuth discovery endpoints for RFC 8414/9728 compliance.
Tests config guards for origin safety (inc_05b).
Each test documents "what bug would still pass this test?"
"""

import pytest
from urllib.parse import urlparse


@pytest.fixture
def set_dev_env(monkeypatch):
    """Set ENV=dev for all tests."""
    monkeypatch.setenv("ENV", "dev")


@pytest.fixture
def set_production_env(monkeypatch):
    """Set production-like env vars for integration tests."""
    monkeypatch.setenv("ENV", "dev")  # Keep dev to avoid prod guards
    monkeypatch.setenv("CLARITY_CLAUDE_OAUTH_ISSUER_BASE", "https://www.priority-guard.com")
    monkeypatch.setenv("CLARITY_CLAUDE_OAUTH_ISSUER_URL", "https://www.priority-guard.com/oauth/pg")


@pytest.fixture(autouse=True)
def restore_mcp_auth_globals():
    """
    Restore clarity.mcp_auth globals after each test.

    Importing mcp_auth_dupl rebinds clarity.mcp_auth globals to Claude config values.
    This fixture saves and restores the original values to prevent cross-test pollution.
    """
    import mcp_server.clarity.mcp_auth as clarity_mcp_auth
    import mcp_server.clarity.config as clarity_config

    # Save original values
    original_values = {
        "mcp_auth.MCP_SERVER_URL": clarity_mcp_auth.MCP_SERVER_URL,
        "mcp_auth.CLARITY_JWKS_URL": clarity_mcp_auth.CLARITY_JWKS_URL,
        "mcp_auth.CLARITY_ISSUER": clarity_mcp_auth.CLARITY_ISSUER,
        "mcp_auth.CLARITY_AUDIENCE": clarity_mcp_auth.CLARITY_AUDIENCE,
        "mcp_auth.TOOL_SCOPES": clarity_mcp_auth.TOOL_SCOPES.copy(),
        "config.MCP_SERVER_URL": clarity_config.MCP_SERVER_URL,
    }

    yield

    # Restore original values
    clarity_mcp_auth.MCP_SERVER_URL = original_values["mcp_auth.MCP_SERVER_URL"]
    clarity_mcp_auth.CLARITY_JWKS_URL = original_values["mcp_auth.CLARITY_JWKS_URL"]
    clarity_mcp_auth.CLARITY_ISSUER = original_values["mcp_auth.CLARITY_ISSUER"]
    clarity_mcp_auth.CLARITY_AUDIENCE = original_values["mcp_auth.CLARITY_AUDIENCE"]
    clarity_mcp_auth.TOOL_SCOPES = original_values["mcp_auth.TOOL_SCOPES"]
    clarity_config.MCP_SERVER_URL = original_values["config.MCP_SERVER_URL"]


class TestOAuthProtectedResource:
    """Tests for oauth_protected_resource() - RFC 9728."""

    @pytest.mark.asyncio
    async def test_authorization_servers_is_root_issuer(self, set_dev_env):
        """
        Test 1: authorization_servers advertises the root issuer (no path).

        Bug that would still pass: regression to path-qualified OAUTH_ISSUER_URL.
        The path-component assertion makes this test meaningful.
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.mindsort_claude.config import OAUTH_ISSUER_BASE

        result = await oauth_protected_resource()

        # Must equal OAUTH_ISSUER_BASE (root issuer, inc_05b hardening)
        assert result["authorization_servers"] == [OAUTH_ISSUER_BASE]

        # Must have no path component (root, not /oauth/pg)
        parsed = urlparse(result["authorization_servers"][0])
        assert parsed.path in ("", "/"), (
            f"authorization_servers must be root issuer (no path), "
            f"got path={parsed.path!r}"
        )

    @pytest.mark.asyncio
    async def test_authorization_servers_from_oauth_issuer_base(self, set_dev_env):
        """
        Test (inc_05b): authorization_servers sourced from OAUTH_ISSUER_BASE.

        Bug that would still pass: leaving inc_05's CLARITY_ISSUER reference
        (functionally fine in prod, but defeats the semantic separation inc_05b
        exists for). This test explicitly verifies the source config var.
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.mindsort_claude.config import OAUTH_ISSUER_BASE, CLARITY_ISSUER

        result = await oauth_protected_resource()

        # Must come from OAUTH_ISSUER_BASE, not CLARITY_ISSUER
        # In dev, these differ: OAUTH_ISSUER_BASE=localhost:8000, CLARITY_ISSUER=www.priority-guard.com
        assert result["authorization_servers"] == [OAUTH_ISSUER_BASE]
        # This would fail if still using CLARITY_ISSUER (different default in dev)
        if OAUTH_ISSUER_BASE != CLARITY_ISSUER:
            assert result["authorization_servers"] != [CLARITY_ISSUER]

    @pytest.mark.asyncio
    async def test_resource_equals_mcp_resource_url(self, set_dev_env):
        """
        Non-regression test: resource field still equals MCP_RESOURCE_URL.

        Bug that would still pass: changing the resource URL accidentally.
        Protects the earlier 02b fix.
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.mindsort_claude.config import MCP_RESOURCE_URL

        result = await oauth_protected_resource()

        assert result["resource"] == MCP_RESOURCE_URL


class TestOAuthAuthorizationServer:
    """Tests for oauth_authorization_server() - RFC 8414."""

    @pytest.mark.asyncio
    async def test_endpoints_remain_path_qualified(self, set_dev_env):
        """
        Test 2: AS-metadata endpoints remain path-qualified (/oauth/pg/).

        Bug that would still pass: over-correction that roots the endpoint URLs
        (which would break the actual OAuth calls Claude makes after discovery).
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_authorization_server

        result = await oauth_authorization_server()

        # All endpoint URLs must contain /oauth/pg/
        assert "/oauth/pg/" in result["authorization_endpoint"]
        assert "/oauth/pg/" in result["token_endpoint"]
        assert "/oauth/pg/" in result["jwks_uri"]
        assert "/oauth/pg/" in result["registration_endpoint"]

    @pytest.mark.asyncio
    async def test_issuer_is_root(self, set_dev_env):
        """
        Test 3: issuer field is the root issuer.

        Bug that would still pass: accidentally swapping issuer to the path value.
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_authorization_server
        from mcp_server.mindsort_claude.config import CLARITY_ISSUER

        result = await oauth_authorization_server()

        assert result["issuer"] == CLARITY_ISSUER


class TestOpenIDConfiguration:
    """Tests for openid_configuration() - OpenID Connect Discovery."""

    @pytest.mark.asyncio
    async def test_endpoints_remain_path_qualified(self, set_dev_env):
        """
        Test 2b: OpenID endpoints remain path-qualified (/oauth/pg/).

        Same rationale as AS-metadata test.
        """
        from mcp_server.mindsort_claude.discovery_dupl import openid_configuration

        result = await openid_configuration()

        # All endpoint URLs must contain /oauth/pg/
        assert "/oauth/pg/" in result["authorization_endpoint"]
        assert "/oauth/pg/" in result["token_endpoint"]
        assert "/oauth/pg/" in result["jwks_uri"]
        assert "/oauth/pg/" in result["registration_endpoint"]

    @pytest.mark.asyncio
    async def test_issuer_is_root(self, set_dev_env):
        """
        Test 3b: issuer field is the root issuer.

        Same rationale as AS-metadata test.
        """
        from mcp_server.mindsort_claude.discovery_dupl import openid_configuration
        from mcp_server.mindsort_claude.config import CLARITY_ISSUER

        result = await openid_configuration()

        assert result["issuer"] == CLARITY_ISSUER


class TestDiscoveryChainIntegration:
    """Integration test: discovery chain resolves correctly."""

    @pytest.mark.asyncio
    async def test_discovery_chain_resolves_to_root_well_known(self, set_dev_env):
        """
        Test 4: Discovery chain resolves to root well-known.

        Takes authorization_servers[0], constructs the well-known URL,
        and asserts it's a root-based URL (not /oauth/pg/.well-known/...).

        Bug that would still pass: any reintroduction of a path-qualified AS
        that field-level unit tests might miss.
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.mindsort_claude.config import OAUTH_ISSUER_BASE

        result = await oauth_protected_resource()
        auth_server = result["authorization_servers"][0]

        # Claude's discovery chain: {authorization_servers[0]}/.well-known/oauth-authorization-server
        well_known_url = f"{auth_server}/.well-known/oauth-authorization-server"

        # Must use the config value (OAUTH_ISSUER_BASE)
        expected = f"{OAUTH_ISSUER_BASE}/.well-known/oauth-authorization-server"
        assert well_known_url == expected, (
            f"Discovery chain must resolve to root well-known.\n"
            f"Got: {well_known_url}\n"
            f"Expected: {expected}"
        )

        # Double-check: must NOT contain /oauth/pg/
        assert "/oauth/pg/" not in well_known_url

        # The authorization_servers value must have no path (or just "/")
        parsed = urlparse(auth_server)
        assert parsed.path in ("", "/"), (
            f"authorization_servers must be root (no path), got path={parsed.path!r}"
        )


class TestConfigGuards:
    """Tests for config.py fail-fast guards (inc_05b)."""

    def test_same_origin_guard_raises_on_differing_origins(self):
        """
        Guard test 1: Same-origin guard RAISES on differing origins.

        Bug that would still pass: a no-op guard (e.g., startswith check
        that passes https://www.example.com.evil.com vs https://www.example.com).

        Uses subprocess because guards run at module import time.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://api.example.com/oauth/pg",  # Different origin!
                "PATH": "",  # Minimal env
            },
            capture_output=True,
            text=True,
        )

        # Must fail with RuntimeError mentioning same origin
        assert result.returncode != 0, "Guard should have raised on differing origins"
        # Tight assertion: must contain "same origin" (not just env var name, which could be ModuleNotFoundError)
        assert "same origin" in result.stderr.lower(), (
            f"Expected 'same origin' in error message, got: {result.stderr}"
        )

    def test_same_origin_guard_passes_legitimate_pairing(self):
        """
        Guard test 2: Same-origin guard PASSES same-origin-different-path.

        Bug that would still pass: an over-strict guard that rejects
        same-origin-different-path (which would break the real config).
        This is the critical asymmetry the guard must get right.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config; print('OK')"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",  # Same origin, different path
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must succeed - same origin with different path is valid
        assert result.returncode == 0, (
            f"Guard should pass same-origin-different-path.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_localhost_in_prod_guard_raises(self):
        """
        Guard test 3: localhost-in-prod guard raises.

        Bug that would still pass: guard not wired to ENV check,
        allowing localhost OAUTH_ISSUER_BASE in production.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "production",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "http://localhost:8000",  # localhost in prod!
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "http://localhost:8000/oauth/pg",
                "CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS": "https://claude.ai",  # Avoid CORS guard
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must fail with RuntimeError mentioning localhost
        assert result.returncode != 0, "Guard should have raised on localhost in production"
        assert "localhost" in result.stderr.lower(), (
            f"Expected localhost error, got: {result.stderr}"
        )

    def test_localhost_guard_does_not_raise_in_dev(self):
        """
        Sanity check: localhost guard does NOT raise in dev mode.

        Bug that would still pass: guard always raises regardless of ENV.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config; print('OK')"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "http://localhost:8000",
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "http://localhost:8000/oauth/pg",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must succeed in dev
        assert result.returncode == 0, (
            f"localhost should be allowed in dev.\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_production_config_loads_with_correct_env_vars(self):
        """
        Guard test (prod happy path): production config loads when all env vars correct.

        Bug that would still pass: a guard that's too strict and rejects valid
        production config. This test ensures the guards don't false-positive.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config; print('OK')"
            ],
            env={
                "ENV": "production",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS": "https://claude.ai",
                "CLARITY_CLAUDE_INTERNAL_API_SECRET": "test-secret",
                # Part C: the audience boot guard requires these two to be set
                # explicitly and byte-exactly equal in production-like ENV.
                # They were previously omitted, so this "correct production
                # config" was in fact incomplete.
                "CLARITY_CLAUDE_MCP_SERVER_URL": "https://mindsort-mcp.priority-guard.com",
                "CLARITY_CLAUDE_AUDIENCE": "https://mindsort-mcp.priority-guard.com/mcp",
                # Part C review fix: the production URL invariants block requires
                # EVERY URL setting to be HTTPS in production. These two were still
                # inheriting their localhost defaults, so this fixture described a
                # production environment that production would refuse to boot.
                "CLARITY_CLAUDE_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
                "CLARITY_CLAUDE_BACKEND_URL": "https://www.priority-guard.com",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must succeed with correct production config
        assert result.returncode == 0, (
            f"Production config should load with correct env vars.\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_env_prod_alias_raises_on_localhost_defaults(self):
        """
        Guard test 5 (inc_05b-fix): ENV=prod + unset OAuth env → MUST raise.

        This is the exact Finding-1 bypass: with ENV=prod (a common alias),
        the old guard using ("production", "staging") would pass, letting
        localhost defaults leak into production.

        Bug that would still pass: _is_production_env() not including "prod".
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "prod",  # Common alias — must be treated as production
                # OAuth env vars NOT set → fall back to localhost defaults
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must fail — "prod" is now treated as production, so localhost guard fires
        assert result.returncode != 0, (
            "ENV=prod should be treated as production and reject localhost defaults.\n"
            f"stderr: {result.stderr}"
        )
        # Assert the localhost guard (not ModuleNotFoundError) fired
        assert "localhost" in result.stderr.lower(), (
            f"Expected localhost error for ENV=prod bypass, got: {result.stderr}"
        )

    def test_unknown_env_raises(self):
        """
        Guard test 6 (inc_05b-fix): ENV=produciton (typo) → MUST raise.

        Defense-in-depth: unknown ENV values are rejected at startup, preventing
        a typo from silently running with dev-mode guards disabled.

        Bug that would still pass: raise-on-unknown-ENV being absent.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "produciton",  # Typo — unknown value
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must fail with "unknown ENV" message
        assert result.returncode != 0, (
            "Unknown ENV value should raise RuntimeError.\n"
            f"stderr: {result.stderr}"
        )
        assert "unknown env" in result.stderr.lower(), (
            f"Expected 'unknown ENV' error, got: {result.stderr}"
        )

    def test_oauth_issuer_base_with_path_raises(self):
        """
        Guard test 7 (inc_05b-fix): OAUTH_ISSUER_BASE with path → MUST raise.

        Finding-2: the same-origin guard only checked (scheme, netloc), so a
        path-qualified value like /oauth/pg would pass but break discovery.

        Bug that would still pass: shape guard missing (origin check but no path check).
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "dev",  # Dev to isolate the shape guard
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com/oauth/pg",  # Path!
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must fail with path-rejection message
        assert result.returncode != 0, (
            "OAUTH_ISSUER_BASE with path should raise RuntimeError.\n"
            f"stderr: {result.stderr}"
        )
        # Assert the path guard (not same-origin or other) fired
        assert "path" in result.stderr.lower() or "root issuer" in result.stderr.lower(), (
            f"Expected path-rejection error, got: {result.stderr}"
        )

    def test_oauth_issuer_base_trailing_slash_normalized(self):
        """
        Guard test 8 (inc_05b-fix): OAUTH_ISSUER_BASE trailing slash → normalized.

        The .rstrip("/") should normalize trailing slash, so the config loads
        AND authorization_servers[0] equals exactly the root (no trailing slash).

        Bug that would still pass: .rstrip("/") missing → trailing slash leaks.
        """
        import subprocess
        import sys

        # Test 1: Config should load without error
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config; print('OK')"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com/",  # Trailing slash
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Trailing slash should be normalized, not rejected.\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

        # Test 2: Verify the normalized value
        result2 = subprocess.run(
            [
                sys.executable, "-c",
                "from mcp_server.mindsort_claude.config import OAUTH_ISSUER_BASE; "
                "print(OAUTH_ISSUER_BASE)"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com/",  # Trailing slash
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result2.returncode == 0, f"stderr: {result2.stderr}"
        # Must be normalized to no trailing slash
        assert result2.stdout.strip() == "https://www.priority-guard.com", (
            f"Expected normalized value without trailing slash, got: {result2.stdout.strip()!r}"
        )

    def test_production_authorization_servers_exact_root(self):
        """
        Guard test 9 (inc_05b-fix): Full production env → authorization_servers exact root.

        End-to-end verification that:
        1. Config imports cleanly with correct production env
        2. authorization_servers[0] equals exactly "https://www.priority-guard.com"

        Bug that would still pass: any guard false-positive OR trailing slash leak
        OR path leak in the advertised value.
        """
        import subprocess
        import sys

        # Test the exact production values
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import asyncio; "
                "from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource; "
                "result = asyncio.run(oauth_protected_resource()); "
                "print(result['authorization_servers'][0])"
            ],
            env={
                "ENV": "production",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS": "https://claude.ai",
                "CLARITY_CLAUDE_INTERNAL_API_SECRET": "test-secret",
                # Part C: the audience boot guard requires these two to be set
                # explicitly and byte-exactly equal in production-like ENV.
                # They were previously omitted, so this "correct production
                # config" was in fact incomplete.
                "CLARITY_CLAUDE_MCP_SERVER_URL": "https://mindsort-mcp.priority-guard.com",
                "CLARITY_CLAUDE_AUDIENCE": "https://mindsort-mcp.priority-guard.com/mcp",
                # Part C review fix: the production URL invariants block requires
                # EVERY URL setting to be HTTPS in production. These two were still
                # inheriting their localhost defaults, so this fixture described a
                # production environment that production would refuse to boot.
                "CLARITY_CLAUDE_JWKS_URL": "https://www.priority-guard.com/oauth/pg/jwks",
                "CLARITY_CLAUDE_BACKEND_URL": "https://www.priority-guard.com",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Production config should load cleanly.\n"
            f"stderr: {result.stderr}"
        )
        # Must be exactly the root — no trailing slash, no path
        assert result.stdout.strip() == "https://www.priority-guard.com", (
            f"authorization_servers[0] must be exact root issuer.\n"
            f"Expected: 'https://www.priority-guard.com'\n"
            f"Got: {result.stdout.strip()!r}"
        )

    def test_env_test_imports_clean(self):
        """
        Guard test 10 (inc_05b addendum): ENV=test → config imports cleanly.

        The inc_05b addendum required "test" and "ci" in the known non-production
        ENV set to avoid breaking test/CI harnesses. A future "cleanup" that
        removes test/ci from _DEV_ENV_VALUES would pass CI silently without this
        test — the exact unverified-guard pattern the addendum forbids.

        Bug that would still pass: removing "test" from _DEV_ENV_VALUES.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config; print('OK')"
            ],
            env={
                "ENV": "test",  # Common test harness value
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"ENV=test should import cleanly (required by inc_05b addendum).\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_env_ci_imports_clean(self):
        """
        Guard test 11 (inc_05b addendum): ENV=ci → config imports cleanly.

        The inc_05b addendum required "test" and "ci" in the known non-production
        ENV set to avoid breaking CI pipelines that use ENV=ci.

        Bug that would still pass: removing "ci" from _DEV_ENV_VALUES.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config; print('OK')"
            ],
            env={
                "ENV": "ci",  # Common CI pipeline value
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"ENV=ci should import cleanly (required by inc_05b addendum).\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_oauth_issuer_base_with_query_raises(self):
        """
        Guard test 12: OAUTH_ISSUER_BASE with query string → MUST raise.

        The root-shape guard rejects query strings, but this was untested.

        Bug that would still pass: refactoring away the query check.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com?foo=bar",
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            "OAUTH_ISSUER_BASE with query string should raise.\n"
            f"stderr: {result.stderr}"
        )
        assert "root issuer" in result.stderr.lower() or "query" in result.stderr.lower(), (
            f"Expected root-shape error, got: {result.stderr}"
        )

    def test_oauth_issuer_base_with_fragment_raises(self):
        """
        Guard test 13: OAUTH_ISSUER_BASE with fragment → MUST raise.

        The root-shape guard rejects fragments, but this was untested.

        Bug that would still pass: refactoring away the fragment check.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com#evil",
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            "OAUTH_ISSUER_BASE with fragment should raise.\n"
            f"stderr: {result.stderr}"
        )
        assert "root issuer" in result.stderr.lower() or "fragment" in result.stderr.lower(), (
            f"Expected root-shape error, got: {result.stderr}"
        )

    def test_same_origin_guard_rejects_scheme_mismatch(self):
        """
        Guard test 14: Same-origin guard rejects http vs https mismatch.

        The guard compares (scheme, netloc) tuples, rejecting scheme mismatches.

        Bug that would still pass: weakening to netloc-only comparison.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": "dev",
                "CLARITY_CLAUDE_OAUTH_ISSUER_BASE": "http://www.priority-guard.com",  # http
                "CLARITY_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",  # https
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            "Scheme mismatch (http vs https) should raise.\n"
            f"stderr: {result.stderr}"
        )
        assert "same origin" in result.stderr.lower(), (
            f"Expected same-origin error, got: {result.stderr}"
        )

    @pytest.mark.parametrize("bad_env", ["Production", " production "])
    def test_env_case_and_whitespace_variants_raise(self, bad_env):
        """
        Guard test 15: ENV case/whitespace variants → MUST raise as unknown.

        Parametrized over:
        - "Production" (capital P) — case variant
        - " production " (leading/trailing whitespace) — whitespace variant

        Both intentionally fail via unknown-ENV guard rather than being
        normalized — maximally explicit, no silent coercion. This test-locks
        the comment in config.py about case/whitespace fail-fast.

        Bug that would still pass: normalizing ENV to lowercase or stripping.
        """
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.mindsort_claude.config"
            ],
            env={
                "ENV": bad_env,  # Not in _KNOWN_ENV_VALUES
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            f"ENV={bad_env!r} should raise as unknown ENV.\n"
            f"stderr: {result.stderr}"
        )
        assert "unknown env" in result.stderr.lower(), (
            f"Expected unknown-ENV error for ENV={bad_env!r}, got: {result.stderr}"
        )
