"""
Live OAuth Discovery Chain Tests — Production Verification.

These tests walk the **deployed** discovery chain over HTTP for each of the
four production MCP servers. They verify the same shape invariants as the
unit tests, but against live responses.

EXCLUDED FROM DEFAULT CI — requires external network access to production.

To run manually:
    pytest -m live tests/integration/oauth_discovery/ -v

Usage:
    Pre-submission: Run before submitting to OpenAI or Anthropic directory
    Pre-deploy: Run after deploying discovery changes before they go live

See doc/ADR_005_platform_oauth_discovery_contracts.md for the invariants.
See doc/OPERATIONS_PRESUBMISSION.md for the full pre-submission checklist.

TEST COVERAGE:
These live tests verify DEPLOYED values — they catch env-value regressions
(e.g., production Render env set to /oauth/pg instead of /oauth/mindsort)
that the unit tests cannot detect. Unit tests verify code-shape invariants
only.
"""

import httpx
import pytest
from urllib.parse import urlparse

# Mark all tests as live (excluded from default runs via addopts = -m "not live")
# To run: pytest -m live tests/integration/oauth_discovery/
pytestmark = pytest.mark.live

# Production URLs for the four MCP servers
# These are the CANONICAL public URLs used in platform submissions.
# Source of truth: doc/CANONICAL_MCP_URLS.md
PRODUCTION_SERVERS = {
    "pg_openai": {
        "url": "https://pg.priority-guard.com",
        "canonical_resource": "https://pg.priority-guard.com/mcp",
    },
    "mindsort_openai": {
        "url": "https://mindsort.priority-guard.com",
        "canonical_resource": "https://mindsort.priority-guard.com/mcp",
    },
    "pg_claude": {
        "url": "https://mcp.priority-guard.com",
        "canonical_resource": "https://mcp.priority-guard.com/mcp",
    },
    "mindsort_claude": {
        "url": "https://mindsort-mcp.priority-guard.com",
        "canonical_resource": "https://mindsort-mcp.priority-guard.com/mcp",
    },
}

# Expected issuer for all servers (one AS)
EXPECTED_ISSUER = "https://www.priority-guard.com"


@pytest.fixture
def http_client():
    """Provide an httpx client with reasonable timeout."""
    return httpx.Client(timeout=30.0, follow_redirects=True)


# =============================================================================
# Shape #1 — PG-OpenAI (mixed-origin)
# =============================================================================

class TestPGOpenAILiveDiscovery:
    """
    Live verification of PG-OpenAI discovery chain (Shape #1).

    Expected shape:
    - PRM authorization_servers = [pg origin]
    - AS metadata token/jwks/register on pg origin
    - issuer + authorization_endpoint on www

    Bug this catches: 5854d50 consolidation regression
    """

    def test_prm_authorization_servers_is_pg_origin(self, http_client):
        """
        PRM authorization_servers must be [pg origin], NOT www.

        This is the exact field 5854d50 broke.
        """
        server = PRODUCTION_SERVERS["pg_openai"]
        url = f"{server['url']}/.well-known/oauth-protected-resource"
        resp = http_client.get(url)
        assert resp.status_code == 200, f"Failed to fetch PRM: {resp.status_code}"

        data = resp.json()
        auth_servers = data.get("authorization_servers", [])

        assert len(auth_servers) == 1
        assert auth_servers[0] == server["url"], \
            f"authorization_servers must be pg origin, got {auth_servers}"
        assert EXPECTED_ISSUER not in auth_servers, \
            "authorization_servers must NOT be www (5854d50 regression)"

    def test_as_metadata_mixed_origin(self, http_client):
        """
        AS metadata at pg origin: token/jwks/register on pg, issuer+authorize on www.
        """
        server = PRODUCTION_SERVERS["pg_openai"]
        url = f"{server['url']}/.well-known/oauth-authorization-server"
        resp = http_client.get(url)
        assert resp.status_code == 200, f"Failed to fetch AS metadata: {resp.status_code}"

        data = resp.json()

        # issuer is www
        assert data["issuer"] == EXPECTED_ISSUER

        # authorization_endpoint on www
        assert data["authorization_endpoint"].startswith(EXPECTED_ISSUER)

        # token/jwks/register on pg origin
        pg_origin = server["url"]
        assert data["token_endpoint"].startswith(pg_origin)
        assert data["jwks_uri"].startswith(pg_origin)
        assert data["registration_endpoint"].startswith(pg_origin)

        # REGRESSION GUARD: token/jwks/register NOT on www
        assert not data["token_endpoint"].startswith(EXPECTED_ISSUER)
        assert not data["jwks_uri"].startswith(EXPECTED_ISSUER)
        assert not data["registration_endpoint"].startswith(EXPECTED_ISSUER)


# =============================================================================
# Shape #2 — MindSort-OpenAI (path-qualified)
# =============================================================================

class TestMindSortOpenAILiveDiscovery:
    """
    Live verification of MindSort-OpenAI discovery chain (Shape #2).

    Expected shape:
    - PRM authorization_servers = [www/oauth/mindsort]
    - All endpoints under that path
    - issuer = www (root)
    """

    def test_prm_authorization_servers_path_qualified(self, http_client):
        """PRM authorization_servers must be path-qualified (.../oauth/mindsort)."""
        server = PRODUCTION_SERVERS["mindsort_openai"]
        url = f"{server['url']}/.well-known/oauth-protected-resource"
        resp = http_client.get(url)
        assert resp.status_code == 200, f"Failed to fetch PRM: {resp.status_code}"

        data = resp.json()
        auth_servers = data.get("authorization_servers", [])

        assert len(auth_servers) == 1
        assert "/oauth/mindsort" in auth_servers[0], \
            f"authorization_servers must be path-qualified, got {auth_servers}"

    def test_as_metadata_follows_path_qualified_chain(self, http_client):
        """
        Follow authorization_servers to fetch AS metadata.
        All endpoints should be under the same path.
        """
        server = PRODUCTION_SERVERS["mindsort_openai"]
        # First fetch PRM to get authorization_servers
        prm_url = f"{server['url']}/.well-known/oauth-protected-resource"
        prm_resp = http_client.get(prm_url)
        assert prm_resp.status_code == 200

        auth_server = prm_resp.json()["authorization_servers"][0]

        # Fetch AS metadata from the advertised authorization_servers
        as_url = f"{auth_server}/.well-known/oauth-authorization-server"
        as_resp = http_client.get(as_url)
        assert as_resp.status_code == 200, \
            f"Failed to fetch AS metadata from {as_url}: {as_resp.status_code}"

        data = as_resp.json()

        # issuer is root
        assert data["issuer"] == EXPECTED_ISSUER

        # Endpoints under the same path as authorization_servers
        assert "/oauth/mindsort/" in data["token_endpoint"]
        assert "/oauth/mindsort/" in data["jwks_uri"]
        assert "/oauth/mindsort/" in data["registration_endpoint"]


# =============================================================================
# Shape #3 — Claude Servers (root issuer)
# =============================================================================

class TestPGClaudeLiveDiscovery:
    """
    Live verification of PG-Claude discovery chain (Shape #3).

    Expected shape:
    - PRM authorization_servers = [www] (root, no path)
    """

    def test_prm_authorization_servers_is_root(self, http_client):
        """PRM authorization_servers must be root issuer (no path)."""
        server = PRODUCTION_SERVERS["pg_claude"]
        url = f"{server['url']}/.well-known/oauth-protected-resource"
        resp = http_client.get(url)
        assert resp.status_code == 200, f"Failed to fetch PRM: {resp.status_code}"

        data = resp.json()
        auth_servers = data.get("authorization_servers", [])

        assert len(auth_servers) == 1

        # Must be root (no path)
        parsed = urlparse(auth_servers[0])
        assert parsed.path in ("", "/"), \
            f"authorization_servers must be root, got path={parsed.path}"


class TestMindSortClaudeLiveDiscovery:
    """
    Live verification of MindSort-Claude discovery chain (Shape #3).

    Expected shape:
    - PRM authorization_servers = [www] (root, no path)
    """

    def test_prm_authorization_servers_is_root(self, http_client):
        """PRM authorization_servers must be root issuer (no path)."""
        server = PRODUCTION_SERVERS["mindsort_claude"]
        url = f"{server['url']}/.well-known/oauth-protected-resource"
        resp = http_client.get(url)
        assert resp.status_code == 200, f"Failed to fetch PRM: {resp.status_code}"

        data = resp.json()
        auth_servers = data.get("authorization_servers", [])

        assert len(auth_servers) == 1

        # Must be root (no path)
        parsed = urlparse(auth_servers[0])
        assert parsed.path in ("", "/"), \
            f"authorization_servers must be root, got path={parsed.path}"


# =============================================================================
# Cross-Cutting — Chain-Following Invariants
# =============================================================================

class TestChainFollowingInvariants:
    """
    Verify S256, response_types, grant_types on the FOLLOWED AS metadata.

    For each server, we:
    1. Fetch PRM to get authorization_servers[0]
    2. Follow that to fetch the actual AS metadata document
    3. Assert invariants on the followed document

    This catches drift in the AS metadata that real clients follow,
    not just the MCP server's local copy.
    """

    @pytest.mark.parametrize("server_name", PRODUCTION_SERVERS.keys())
    def test_followed_as_metadata_s256(self, http_client, server_name):
        """
        Follow the discovery chain and verify S256 is advertised.

        Claude refuses to connect if S256 is not in code_challenge_methods_supported.
        """
        server = PRODUCTION_SERVERS[server_name]

        # Step 1: Fetch PRM
        prm_url = f"{server['url']}/.well-known/oauth-protected-resource"
        prm_resp = http_client.get(prm_url)
        assert prm_resp.status_code == 200, f"{server_name}: Failed to fetch PRM"

        auth_server = prm_resp.json()["authorization_servers"][0]

        # Step 2: Follow to AS metadata
        as_url = f"{auth_server}/.well-known/oauth-authorization-server"
        as_resp = http_client.get(as_url)
        assert as_resp.status_code == 200, \
            f"{server_name}: Failed to fetch AS metadata from {as_url}"

        data = as_resp.json()
        methods = data.get("code_challenge_methods_supported", [])
        assert methods == ["S256"], \
            f"{server_name}: code_challenge_methods_supported must be ['S256'], got {methods}"

    @pytest.mark.parametrize("server_name", PRODUCTION_SERVERS.keys())
    def test_followed_as_metadata_response_types(self, http_client, server_name):
        """Follow chain and verify response_types_supported = ["code"]."""
        server = PRODUCTION_SERVERS[server_name]

        prm_url = f"{server['url']}/.well-known/oauth-protected-resource"
        prm_resp = http_client.get(prm_url)
        assert prm_resp.status_code == 200

        auth_server = prm_resp.json()["authorization_servers"][0]
        as_url = f"{auth_server}/.well-known/oauth-authorization-server"
        as_resp = http_client.get(as_url)
        assert as_resp.status_code == 200

        data = as_resp.json()
        types = data.get("response_types_supported", [])
        assert types == ["code"], \
            f"{server_name}: response_types_supported must be ['code'], got {types}"

    @pytest.mark.parametrize("server_name", PRODUCTION_SERVERS.keys())
    def test_followed_as_metadata_grant_types(self, http_client, server_name):
        """Follow chain and verify grant_types exactly."""
        server = PRODUCTION_SERVERS[server_name]

        prm_url = f"{server['url']}/.well-known/oauth-protected-resource"
        prm_resp = http_client.get(prm_url)
        assert prm_resp.status_code == 200

        auth_server = prm_resp.json()["authorization_servers"][0]
        as_url = f"{auth_server}/.well-known/oauth-authorization-server"
        as_resp = http_client.get(as_url)
        assert as_resp.status_code == 200

        data = as_resp.json()
        grants = set(data.get("grant_types_supported", []))
        expected = {"authorization_code", "refresh_token"}
        assert grants == expected, \
            f"{server_name}: grant_types_supported must be exactly {expected}, got {grants}"


# =============================================================================
# PRM Resource + 401 Compliance (Claude requirements)
# =============================================================================

class TestPRMResourceCompliance:
    """
    Verify PRM resource field matches canonical public URL.

    Per Claude compliance checklist: the resource claim must match the
    URL in the Anthropic submission (the URL users connect to).
    """

    @pytest.mark.parametrize("server_name", PRODUCTION_SERVERS.keys())
    def test_prm_resource_matches_canonical(self, http_client, server_name):
        """PRM resource must equal the canonical public URL."""
        server = PRODUCTION_SERVERS[server_name]

        prm_url = f"{server['url']}/.well-known/oauth-protected-resource"
        resp = http_client.get(prm_url)
        assert resp.status_code == 200, f"{server_name}: Failed to fetch PRM"

        data = resp.json()
        resource = data.get("resource")

        assert resource == server["canonical_resource"], (
            f"{server_name}: PRM resource mismatch. "
            f"Expected {server['canonical_resource']}, got {resource}"
        )


class TestUnauthenticatedMCPEndpoint:
    """
    Verify unauthenticated POST /mcp returns 401 with WWW-Authenticate.

    Per Claude compliance checklist: the MCP endpoint must return
    WWW-Authenticate header with resource_metadata pointer on 401.
    """

    @pytest.mark.parametrize("server_name", [
        "pg_openai",
        pytest.param(
            "mindsort_openai",
            marks=pytest.mark.xfail(
                strict=True,
                reason=(
                    "MindSort-OpenAI implements tool-level OAuth (official pattern #2 per OpenAI Apps SDK); "
                    "anonymous handshake allowed, per-tool securitySchemes triggers auth UI. "
                    "See doc/OAuth/platform_quirk_mindsort_openai_401.md (documented pattern record)."
                ),
            ),
        ),
        "pg_claude",
        "mindsort_claude",
    ])
    def test_post_mcp_returns_401_with_www_authenticate(self, http_client, server_name):
        """
        POST /mcp without auth must return 401 with WWW-Authenticate
        containing resource_metadata.
        """
        server = PRODUCTION_SERVERS[server_name]

        # POST to /mcp without Authorization header
        mcp_url = f"{server['url']}/mcp"
        resp = http_client.post(mcp_url, content=b"", headers={"Content-Type": "application/json"})

        assert resp.status_code == 401, \
            f"{server_name}: Expected 401 for unauthenticated /mcp, got {resp.status_code}"

        www_auth = resp.headers.get("WWW-Authenticate", "")
        # Claude requirement: WWW-Authenticate must contain resource_metadata pointer
        # Bearer alone is insufficient for Claude's RFC 9728 flow
        assert "resource_metadata" in www_auth.lower(), (
            f"{server_name}: WWW-Authenticate header must contain resource_metadata pointer "
            f"(required by Claude RFC 9728 flow). Got: {www_auth}"
        )
