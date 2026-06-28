"""
MindSort Claude MCP Server discovery tests (inc_05).

Tests OAuth discovery endpoints for RFC 8414/9728 compliance.
Each test documents "what bug would still pass this test?"
"""

import pytest
from urllib.parse import urlparse


@pytest.fixture
def set_dev_env(monkeypatch):
    """Set ENV=dev for all tests."""
    monkeypatch.setenv("ENV", "dev")


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
        from mcp_server.mindsort_claude.config import CLARITY_ISSUER

        result = await oauth_protected_resource()

        # Must equal CLARITY_ISSUER (root issuer)
        assert result["authorization_servers"] == [CLARITY_ISSUER]

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
        and asserts it equals the root-based URL (not /oauth/pg/.well-known/...).

        Bug that would still pass: any reintroduction of a path-qualified AS
        that field-level unit tests might miss.
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource

        result = await oauth_protected_resource()
        auth_server = result["authorization_servers"][0]

        # Claude's discovery chain: {authorization_servers[0]}/.well-known/oauth-authorization-server
        well_known_url = f"{auth_server}/.well-known/oauth-authorization-server"

        # Must be root-based, NOT path-qualified
        expected = "https://www.priority-guard.com/.well-known/oauth-authorization-server"
        assert well_known_url == expected, (
            f"Discovery chain must resolve to root well-known.\n"
            f"Got: {well_known_url}\n"
            f"Expected: {expected}"
        )

        # Double-check: must NOT contain /oauth/pg/
        assert "/oauth/pg/" not in well_known_url
