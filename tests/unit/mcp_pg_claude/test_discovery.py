"""
Priority Guardian Claude MCP Server discovery tests (inc_config_hardening_parity).

Tests OAuth discovery endpoints for RFC 8414/9728 compliance.
Tests config guards for origin safety (back-port of inc_05b hardening).
Each test documents "what bug would still pass this test?"
"""

import subprocess
import sys

import pytest
from urllib.parse import urlparse


@pytest.fixture
def set_dev_env(monkeypatch):
    """Set ENV=dev for all tests."""
    monkeypatch.setenv("ENV", "dev")


class TestConfigGuards:
    """Tests for config.py fail-fast guards (inc_config_hardening_parity)."""

    def test_unknown_env_raises(self):
        """
        Guard test 1: ENV=produciton (typo) → MUST raise.

        Defense-in-depth: unknown ENV values are rejected at startup, preventing
        a typo from silently running with dev-mode guards disabled.

        Bug that would still pass: raise-on-unknown-ENV being absent.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
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

    def test_env_test_imports_clean(self):
        """
        Guard test 2: ENV=test → config imports cleanly.

        The known-ENV set must include "test" to avoid breaking test harnesses.

        Bug that would still pass: removing "test" from _DEV_ENV_VALUES.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config; print('OK')"
            ],
            env={
                "ENV": "test",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"ENV=test should import cleanly.\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_env_ci_imports_clean(self):
        """
        Guard test 3: ENV=ci → config imports cleanly.

        The known-ENV set must include "ci" to avoid breaking CI pipelines.

        Bug that would still pass: removing "ci" from _DEV_ENV_VALUES.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config; print('OK')"
            ],
            env={
                "ENV": "ci",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"ENV=ci should import cleanly.\n"
            f"stderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_oauth_issuer_base_with_path_raises(self):
        """
        Guard test 4: OAUTH_ISSUER_BASE with path → MUST raise.

        A path-qualified value like /oauth/pg would break Claude discovery
        (authorization_servers must be root).

        Bug that would still pass: shape guard missing.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "dev",  # Dev to isolate the shape guard
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com/oauth/pg",  # Path!
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
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
        Guard test 5: OAUTH_ISSUER_BASE trailing slash → normalized.

        The .rstrip("/") should normalize trailing slash, so the config loads
        AND OAUTH_ISSUER_BASE equals exactly the root (no trailing slash).

        Bug that would still pass: .rstrip("/") missing → trailing slash leaks.
        """
        # Test 1: Config should load without error
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config; print('OK')"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com/",  # Trailing slash
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
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
                "from mcp_server.priority_guardian_claude.config import OAUTH_ISSUER_BASE; "
                "print(OAUTH_ISSUER_BASE)"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com/",  # Trailing slash
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
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

    def test_env_prod_alias_raises_on_localhost_defaults(self):
        """
        Guard test 6: ENV=prod + unset OAuth env → MUST raise via localhost guard.

        Ensures the "prod" alias is treated as production. PG's existing tuples
        already include "prod", so this locks that behavior against regression.

        Bug that would still pass: _is_production_env() not including "prod".
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "prod",  # Common alias — must be treated as production
                # OAuth env vars NOT set → fall back to localhost defaults
                # Provide secret and CORS to bypass those guards and reach localhost guard
                "PG_CLAUDE_INTERNAL_API_SECRET": "test-secret",
                "PG_CLAUDE_CORS_ALLOWED_ORIGINS": "https://claude.ai",
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must fail — "prod" is treated as production, so localhost guard fires
        assert result.returncode != 0, (
            "ENV=prod should be treated as production and reject localhost defaults.\n"
            f"stderr: {result.stderr}"
        )
        # Assert the localhost guard (not ModuleNotFoundError) fired
        assert "localhost" in result.stderr.lower(), (
            f"Expected localhost error for ENV=prod bypass, got: {result.stderr}"
        )

    def test_production_happy_path(self):
        """
        Guard test 7: Full production env → config imports cleanly,
        authorization_servers[0] equals exactly "https://www.priority-guard.com".

        Bug that would still pass: guard false-positive on real deployed config.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import asyncio; "
                "from mcp_server.priority_guardian_claude.discovery_dupl import oauth_protected_resource; "
                "result = asyncio.run(oauth_protected_resource()); "
                "print(result['authorization_servers'][0])"
            ],
            env={
                "ENV": "production",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
                "PG_CLAUDE_CORS_ALLOWED_ORIGINS": "https://claude.ai",
                "PG_CLAUDE_INTERNAL_API_SECRET": "test-secret",
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

    def test_same_origin_guard_raises_on_differing_origins(self):
        """
        Guard test 8: Same-origin guard RAISES on differing origins.

        Bug that would still pass: a no-op guard (e.g., startswith check
        that passes https://www.example.com.evil.com vs https://www.example.com).
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://api.example.com/oauth/pg",  # Different origin!
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        # Must fail with RuntimeError mentioning same origin
        assert result.returncode != 0, "Guard should have raised on differing origins"
        assert "same origin" in result.stderr.lower(), (
            f"Expected 'same origin' in error message, got: {result.stderr}"
        )

    def test_same_origin_guard_passes_legitimate_pairing(self):
        """
        Guard test 9: Same-origin guard PASSES same-origin-different-path.

        Bug that would still pass: an over-strict guard that rejects
        same-origin-different-path (which would break the real config).
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config; print('OK')"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com",
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
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
        Guard test 10: localhost-in-prod guard raises.

        Bug that would still pass: guard not wired to ENV check.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "production",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "http://localhost:8000",  # localhost in prod!
                "PG_CLAUDE_OAUTH_ISSUER_URL": "http://localhost:8000/oauth/pg",
                "PG_CLAUDE_CORS_ALLOWED_ORIGINS": "https://claude.ai",
                "PG_CLAUDE_INTERNAL_API_SECRET": "test-secret",  # Bypass secret guard
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
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config; print('OK')"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "http://localhost:8000",
                "PG_CLAUDE_OAUTH_ISSUER_URL": "http://localhost:8000/oauth/pg",
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

    def test_oauth_issuer_base_with_query_raises(self):
        """
        Guard test 12: OAUTH_ISSUER_BASE with query string → MUST raise.

        The root-shape guard rejects query strings, but this was untested.

        Bug that would still pass: refactoring away the query check.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com?foo=bar",
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
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
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "https://www.priority-guard.com#evil",
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",
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
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "dev",
                "PG_CLAUDE_OAUTH_ISSUER_BASE": "http://www.priority-guard.com",  # http
                "PG_CLAUDE_OAUTH_ISSUER_URL": "https://www.priority-guard.com/oauth/pg",  # https
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

    def test_env_uppercase_production_raises(self):
        """
        Guard test 15: ENV=Production (capital P) → MUST raise as unknown.

        Case variants intentionally fail via unknown-ENV guard rather than
        being normalized — maximally explicit, no silent coercion.

        Bug that would still pass: normalizing ENV to lowercase.
        """
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import mcp_server.priority_guardian_claude.config"
            ],
            env={
                "ENV": "Production",  # Capital P — not in _KNOWN_ENV_VALUES
                "PATH": "",
            },
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            "ENV=Production should raise as unknown ENV.\n"
            f"stderr: {result.stderr}"
        )
        assert "unknown env" in result.stderr.lower(), (
            f"Expected unknown-ENV error, got: {result.stderr}"
        )


class TestOAuthProtectedResource:
    """Tests for oauth_protected_resource() - RFC 9728."""

    @pytest.mark.asyncio
    async def test_authorization_servers_is_root_issuer(self, set_dev_env):
        """
        Test: authorization_servers advertises the root issuer (no path).

        Bug that would still pass: regression to path-qualified OAUTH_ISSUER_URL.
        """
        from mcp_server.priority_guardian_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.priority_guardian_claude.config import OAUTH_ISSUER_BASE

        result = await oauth_protected_resource()

        # Must equal OAUTH_ISSUER_BASE (root issuer)
        assert result["authorization_servers"] == [OAUTH_ISSUER_BASE]

        # Must have no path component (root, not /oauth/pg)
        parsed = urlparse(result["authorization_servers"][0])
        assert parsed.path in ("", "/"), (
            f"authorization_servers must be root issuer (no path), "
            f"got path={parsed.path!r}"
        )

    @pytest.mark.asyncio
    async def test_resource_equals_mcp_resource_url(self, set_dev_env):
        """
        Non-regression test: resource field still equals MCP_RESOURCE_URL.

        Bug that would still pass: changing the resource URL accidentally.
        """
        from mcp_server.priority_guardian_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.priority_guardian_claude.config import MCP_RESOURCE_URL

        result = await oauth_protected_resource()

        assert result["resource"] == MCP_RESOURCE_URL


class TestOAuthAuthorizationServer:
    """Tests for oauth_authorization_server() - RFC 8414."""

    @pytest.mark.asyncio
    async def test_endpoints_remain_path_qualified(self, set_dev_env):
        """
        Test: AS-metadata endpoints remain path-qualified (/oauth/pg/).

        Bug that would still pass: over-correction that roots the endpoint URLs.
        """
        from mcp_server.priority_guardian_claude.discovery_dupl import oauth_authorization_server

        result = await oauth_authorization_server()

        # All endpoint URLs must contain /oauth/pg/
        assert "/oauth/pg/" in result["authorization_endpoint"]
        assert "/oauth/pg/" in result["token_endpoint"]
        assert "/oauth/pg/" in result["jwks_uri"]
        assert "/oauth/pg/" in result["registration_endpoint"]

    @pytest.mark.asyncio
    async def test_issuer_is_root(self, set_dev_env):
        """
        Test: issuer field is the root issuer (OAUTH_ISSUER_BASE).

        Bug that would still pass: accidentally swapping issuer to the path value.
        """
        from mcp_server.priority_guardian_claude.discovery_dupl import oauth_authorization_server
        from mcp_server.priority_guardian_claude.config import OAUTH_ISSUER_BASE

        result = await oauth_authorization_server()

        # discovery_dupl uses OAUTH_ISSUER_BASE for issuer (Shape #3 — root issuer)
        assert result["issuer"] == OAUTH_ISSUER_BASE
