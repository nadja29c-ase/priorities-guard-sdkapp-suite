"""
Unit tests for MCP discovery endpoint URL consistency.

Tests verify that discovery endpoints return the DELIBERATELY MIXED-ORIGIN
shape that ChatGPT's MCP OAuth flow requires. This shape is load-bearing —
see mcp_server/priority_guardian/discovery.py NOTE block and
claude increments/SHARED ARCHITECTURE/hotfix_pg_openai_discovery_restore.md.

The working shape (restored after the 5854d50 regression):
  issuer                 = OAUTH_ISSUER_BASE        (www) — matches token iss claim
  authorization_endpoint = OAUTH_ISSUER_BASE/oauth/pg/authorize (www) — browser popup
  token_endpoint         = MCP_SERVER_URL/oauth/token    (pg) — same-origin proxy route
  jwks_uri               = MCP_SERVER_URL/oauth/jwks     (pg) — same-origin proxy route
  registration_endpoint  = MCP_SERVER_URL/oauth/register (pg) — same-origin proxy route
  authorization_servers  = [MCP_SERVER_URL]              (pg) — ChatGPT discovers AS at RS origin

WHY MIXED (do not "consolidate" to a single origin):
ChatGPT discovers the AS via authorization_servers, then calls
token/jwks/register on THAT SAME origin (pg). Pointing those at www (a
different origin) makes ChatGPT complete OAuth but silently abandon the
connection before calling /mcp — the exact 5854d50 production regression.
Meanwhile issuer must stay www so it matches the token's `iss` claim (minted
by the backend as www). These two constraints are only satisfiable by the
mixed-origin shape. If you are tempted to make all origins equal "for
consistency," reproduce a full ChatGPT PG reconnect first — that cleanup is
what broke production on 2026-06-30.
"""

import pytest


class TestDiscoveryConsistency:
    """Tests that lock the restored mixed-origin discovery shape."""

    @pytest.mark.asyncio
    async def test_openid_configuration_mixed_origin_shape(self):
        """openid_configuration: issuer+authorize on www (OAUTH_ISSUER_BASE);
        token/jwks/register on pg (MCP_SERVER_URL)."""
        from mcp_server.priority_guardian.discovery import openid_configuration
        from mcp_server.priority_guardian.config import OAUTH_ISSUER_BASE, MCP_SERVER_URL

        result = await openid_configuration()

        # issuer must equal OAUTH_ISSUER_BASE (www) so it matches the token iss claim
        assert result["issuer"] == OAUTH_ISSUER_BASE

        # authorization_endpoint is the backend (www) — browser popup, no same-origin need
        assert result["authorization_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["authorization_endpoint"] == f"{OAUTH_ISSUER_BASE}/oauth/pg/authorize"

        # token/jwks/register MUST be on the MCP origin (pg) — same-origin proxy routes
        # that ChatGPT calls against the discovered authorization_servers origin.
        assert result["token_endpoint"] == f"{MCP_SERVER_URL}/oauth/token"
        assert result["jwks_uri"] == f"{MCP_SERVER_URL}/oauth/jwks"
        assert result["registration_endpoint"] == f"{MCP_SERVER_URL}/oauth/register"

        # Guard the regression directly: these three must NOT be on the www origin.
        assert not result["token_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert not result["jwks_uri"].startswith(OAUTH_ISSUER_BASE)
        assert not result["registration_endpoint"].startswith(OAUTH_ISSUER_BASE)

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_mixed_origin_shape(self):
        """oauth_authorization_server: same mixed-origin shape as openid_configuration."""
        from mcp_server.priority_guardian.discovery import oauth_authorization_server
        from mcp_server.priority_guardian.config import OAUTH_ISSUER_BASE, MCP_SERVER_URL

        result = await oauth_authorization_server()

        assert result["issuer"] == OAUTH_ISSUER_BASE
        assert result["authorization_endpoint"] == f"{OAUTH_ISSUER_BASE}/oauth/pg/authorize"

        assert result["token_endpoint"] == f"{MCP_SERVER_URL}/oauth/token"
        assert result["jwks_uri"] == f"{MCP_SERVER_URL}/oauth/jwks"
        assert result["registration_endpoint"] == f"{MCP_SERVER_URL}/oauth/register"

        # Regression guard: token/jwks/register must not collapse to the www origin.
        assert not result["token_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert not result["jwks_uri"].startswith(OAUTH_ISSUER_BASE)
        assert not result["registration_endpoint"].startswith(OAUTH_ISSUER_BASE)

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_advertises_mcp_origin_as_auth_server(self):
        """oauth_protected_resource: resource is the MCP resource URL; authorization_servers
        points at the MCP origin (pg), NOT the backend root (www).

        This is the single field 5854d50 broke: advertising the www root made ChatGPT
        unable to complete the discovery->token chain on a coherent origin.
        """
        from mcp_server.priority_guardian.discovery import oauth_protected_resource
        from mcp_server.priority_guardian.config import (
            MCP_SERVER_URL,
            MCP_RESOURCE_URL,
            OAUTH_ISSUER_BASE,
        )

        result = await oauth_protected_resource()

        # resource is the full MCP resource URL (.../mcp)
        assert result["resource"] == MCP_RESOURCE_URL

        # authorization_servers MUST be exactly [MCP_SERVER_URL] (pg origin).
        assert result["authorization_servers"] == [MCP_SERVER_URL]

        # Regression guard: must NOT advertise the backend root (www) as the auth server.
        assert OAUTH_ISSUER_BASE not in result["authorization_servers"]

    @pytest.mark.asyncio
    async def test_discovery_scopes_match_config(self):
        """All discovery endpoints should return scopes_supported matching config."""
        from mcp_server.priority_guardian.discovery import (
            openid_configuration,
            oauth_authorization_server,
            oauth_protected_resource,
        )
        from mcp_server.priority_guardian.config import SCOPES_SUPPORTED

        oidc = await openid_configuration()
        oauth_as = await oauth_authorization_server()
        oauth_pr = await oauth_protected_resource()

        # All three should have scopes_supported matching config
        assert oidc["scopes_supported"] == SCOPES_SUPPORTED
        assert oauth_as["scopes_supported"] == SCOPES_SUPPORTED
        assert oauth_pr["scopes_supported"] == SCOPES_SUPPORTED

    @pytest.mark.asyncio
    async def test_code_challenge_methods_include_s256(self):
        """openid_configuration and oauth_authorization_server should include S256."""
        from mcp_server.priority_guardian.discovery import (
            openid_configuration,
            oauth_authorization_server,
        )

        oidc = await openid_configuration()
        oauth_as = await oauth_authorization_server()

        # Both should have code_challenge_methods_supported with S256
        assert "code_challenge_methods_supported" in oidc
        assert "S256" in oidc["code_challenge_methods_supported"]

        assert "code_challenge_methods_supported" in oauth_as
        assert "S256" in oauth_as["code_challenge_methods_supported"]
