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
        assert "same origin" in result.stderr.lower() or "CLARITY_CLAUDE_OAUTH_ISSUER" in result.stderr, (
            f"Expected same-origin error, got: {result.stderr}"
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
