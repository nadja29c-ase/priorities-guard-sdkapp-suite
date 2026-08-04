"""
OAuth Discovery Contract Tests — Platform-Specific Shape Invariants.

These tests lock the three intentional OAuth discovery shapes described in
ADR_005_platform_oauth_discovery_contracts.md. They convert load-bearing
production behavior into CI-enforced invariants.

Shape #1 — PG-OpenAI (mixed-origin):
  - authorization_servers = [MCP_SERVER_URL] (RS origin, NOT www)
  - token/jwks/register on RS origin (same-origin proxy routes)
  - issuer + authorization_endpoint on www (backend)
  - WHY: ChatGPT requires same-origin discovery→token chain

Shape #2 — MindSort-OpenAI (path-qualified):
  - authorization_servers = [OAUTH_ISSUER_URL] (path-qualified, .../oauth/mindsort)
  - token/jwks/register under that same path
  - issuer = root www
  - WHY: Self-coherent www chain; ChatGPT tolerates issuer(root) ≠ discovery path

Shape #3 — PG-Claude + MindSort-Claude (root issuer):
  - authorization_servers = [OAUTH_ISSUER_BASE] (root, no path)
  - issuer = root www
  - WHY: Claude's RFC 8414/9728-literal discovery requires root issuer

Regression guards:
- Shape #1: FAILS if token/jwks/register consolidated to www (re-detects 5854d50)
- Shape #3: FAILS if authorization_servers becomes path-qualified (re-detects pre-inc_05 bug)

Cross-cutting invariants:
- code_challenge_methods_supported == ["S256"] (never plain)
- response_types_supported == ["code"]
- grant_types == ["authorization_code", "refresh_token"]

History:
- 2026-06-30: Commit 5854d50 consolidated PG-OpenAI to all-www, breaking ChatGPT.
- 2026-07-02: This test module created per inc_oauth_discovery_contracts.

Migrated from: tests/unit/mcp_priority_guardian/test_discovery_consistency.py (retired)

TEST COVERAGE BOUNDARY (unit vs live):
These unit tests verify CODE-SHAPE invariants — they catch regressions where the
discovery code is changed to emit the wrong URL structure (e.g., re-applying 5854d50's
consolidation, or path-qualifying Claude's authorization_servers). They run against
dev-default config values loaded at import time.

ENV-VALUE regressions (e.g., production Render env set to /oauth/pg instead of
/oauth/mindsort, causing live MindSort breakage) are NOT caught by these unit tests.
Those are caught by the LIVE suite:
    tests/integration/oauth_discovery/test_live_discovery_chain.py

The live tests are excluded from default pytest runs (marker: live). They must be
run manually pre-deploy/pre-submission:
    pytest -m live tests/integration/oauth_discovery/ -v

See doc/ADR/ADR_005_platform_oauth_discovery_contracts.md for the full rationale.
"""

import pytest
from urllib.parse import urlparse


# =============================================================================
# Shape #1 — PG-OpenAI (mixed-origin)
# =============================================================================

class TestPGOpenAIDiscoveryShape:
    """
    Tests for Priority Guardian OpenAI MCP server discovery (Shape #1).

    The working shape is DELIBERATELY mixed-origin:
    - issuer + authorization_endpoint on www (backend)
    - token/jwks/register + authorization_servers on pg (RS origin)

    This satisfies ChatGPT's same-origin discovery→token chain requirement
    while keeping issuer=www to match the token's iss claim.

    Bug this catches: 5854d50 consolidation regression (2026-06-30)
    """

    @pytest.mark.asyncio
    async def test_openid_configuration_mixed_origin_shape(self):
        """
        openid_configuration must return mixed-origin shape:
        - issuer + authorize on www (OAUTH_ISSUER_BASE)
        - token/jwks/register on pg (MCP_SERVER_URL)

        Bug caught: 5854d50 moved token/jwks/register to www, breaking ChatGPT.
        """
        from mcp_server.priority_guardian.discovery import openid_configuration
        from mcp_server.priority_guardian.config import OAUTH_ISSUER_BASE, MCP_SERVER_URL

        result = await openid_configuration()

        # issuer must be OAUTH_ISSUER_BASE (www) — matches token iss claim
        assert result["issuer"] == OAUTH_ISSUER_BASE

        # authorization_endpoint on www (browser popup, no same-origin need)
        assert result["authorization_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["authorization_endpoint"] == f"{OAUTH_ISSUER_BASE}/oauth/pg/authorize"

        # token/jwks/register MUST be on MCP origin (pg) — same-origin proxy routes
        assert result["token_endpoint"] == f"{MCP_SERVER_URL}/oauth/token"
        assert result["jwks_uri"] == f"{MCP_SERVER_URL}/oauth/jwks"
        assert result["registration_endpoint"] == f"{MCP_SERVER_URL}/oauth/register"

        # REGRESSION GUARD: These MUST NOT be on www (the 5854d50 bug)
        assert not result["token_endpoint"].startswith(OAUTH_ISSUER_BASE), \
            "token_endpoint on www breaks ChatGPT same-origin chain (5854d50 regression)"
        assert not result["jwks_uri"].startswith(OAUTH_ISSUER_BASE), \
            "jwks_uri on www breaks ChatGPT same-origin chain (5854d50 regression)"
        assert not result["registration_endpoint"].startswith(OAUTH_ISSUER_BASE), \
            "registration_endpoint on www breaks ChatGPT same-origin chain (5854d50 regression)"

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

        # Regression guard: not on www
        assert not result["token_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert not result["jwks_uri"].startswith(OAUTH_ISSUER_BASE)
        assert not result["registration_endpoint"].startswith(OAUTH_ISSUER_BASE)

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_advertises_mcp_origin(self):
        """
        oauth_protected_resource: authorization_servers MUST be [MCP_SERVER_URL] (pg origin).

        This is the single field 5854d50 broke: advertising www root made ChatGPT
        unable to complete the discovery→token chain on a coherent origin.

        Bug caught: 5854d50 changed this to [OAUTH_ISSUER_BASE] (www)
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

        # authorization_servers MUST be [MCP_SERVER_URL] (pg origin)
        assert result["authorization_servers"] == [MCP_SERVER_URL]

        # REGRESSION GUARD: MUST NOT advertise www as the auth server
        assert OAUTH_ISSUER_BASE not in result["authorization_servers"], \
            "authorization_servers pointing to www breaks ChatGPT (5854d50 regression)"


# =============================================================================
# Shape #2 — MindSort-OpenAI (path-qualified)
# =============================================================================

class TestMindSortOpenAIDiscoveryShape:
    """
    Tests for MindSort OpenAI MCP server discovery (Shape #2).

    The working shape uses path-qualified authorization_servers:
    - authorization_servers = [OAUTH_ISSUER_URL] (e.g., .../oauth/mindsort)
    - All endpoints under that same path
    - issuer = root www

    This gives MindSort a self-coherent www chain without cross-origin proxying.
    ChatGPT tolerates issuer(root) ≠ discovery path.
    """

    @pytest.mark.asyncio
    async def test_openid_configuration_path_qualified_chain(self):
        """
        MindSort-OpenAI openid_configuration must use path-qualified endpoints.
        All endpoints should be under OAUTH_ISSUER_URL (e.g., .../oauth/mindsort/).
        """
        from mcp_server.clarity.discovery import openid_configuration
        from mcp_server.clarity.config import CLARITY_ISSUER, OAUTH_ISSUER_URL

        result = await openid_configuration()

        # issuer is root (CLARITY_ISSUER = https://www.priority-guard.com)
        assert result["issuer"] == CLARITY_ISSUER

        # All endpoints under OAUTH_ISSUER_URL (path-qualified)
        assert result["authorization_endpoint"] == f"{OAUTH_ISSUER_URL}/authorize"
        assert result["token_endpoint"] == f"{OAUTH_ISSUER_URL}/token"
        assert result["jwks_uri"] == f"{OAUTH_ISSUER_URL}/jwks"
        assert result["registration_endpoint"] == f"{OAUTH_ISSUER_URL}/register"

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_path_qualified_chain(self):
        """
        MindSort-OpenAI oauth_authorization_server must match openid_configuration.

        Bug caught: editing one function but not the twin would pass CI without this.
        """
        from mcp_server.clarity.discovery import oauth_authorization_server
        from mcp_server.clarity.config import CLARITY_ISSUER, OAUTH_ISSUER_URL

        result = await oauth_authorization_server()

        assert result["issuer"] == CLARITY_ISSUER
        assert result["authorization_endpoint"] == f"{OAUTH_ISSUER_URL}/authorize"
        assert result["token_endpoint"] == f"{OAUTH_ISSUER_URL}/token"
        assert result["jwks_uri"] == f"{OAUTH_ISSUER_URL}/jwks"
        assert result["registration_endpoint"] == f"{OAUTH_ISSUER_URL}/register"

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_path_qualified_auth_servers(self):
        """
        MindSort-OpenAI PRM: authorization_servers must be [OAUTH_ISSUER_URL] (path-qualified).

        Chain coherence (authorization_servers origin == AS metadata endpoints origin)
        is enforced transitively: this test asserts authorization_servers == OAUTH_ISSUER_URL,
        and test_openid_configuration_path_qualified_chain asserts all endpoints are under
        that same OAUTH_ISSUER_URL.
        """
        from mcp_server.clarity.discovery import oauth_protected_resource
        from mcp_server.clarity.config import MCP_SERVER_URL, OAUTH_ISSUER_URL

        result = await oauth_protected_resource()

        # authorization_servers is path-qualified
        assert result["authorization_servers"] == [OAUTH_ISSUER_URL]

        # resource is the MCP resource URL
        assert result["resource"] == f"{MCP_SERVER_URL}/mcp"


# =============================================================================
# Shape #3 — Claude Servers (root issuer)
# =============================================================================

class TestPGClaudeDiscoveryShape:
    """
    Tests for Priority Guardian Claude MCP server discovery (Shape #3).

    Claude's RFC 8414/9728-literal discovery requires:
    - authorization_servers = [OAUTH_ISSUER_BASE] (root, no path)
    - issuer = root

    Bug caught: pre-inc_05 had path-qualified authorization_servers, failing Claude DCR.
    """

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_root_issuer(self):
        """
        PG-Claude PRM: authorization_servers must be root issuer (no path).

        Claude's RFC-literal discovery chain requires authorization_servers
        to match the AS's self-declared issuer (root).

        Bug caught: pre-inc_05 used path-qualified authorization_servers
        """
        from mcp_server.priority_guardian_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.priority_guardian_claude.config import (
            MCP_RESOURCE_URL,
            OAUTH_ISSUER_BASE,
        )

        result = await oauth_protected_resource()

        # authorization_servers MUST be root issuer
        assert result["authorization_servers"] == [OAUTH_ISSUER_BASE]

        # REGRESSION GUARD: authorization_servers must be a root (no path)
        auth_server = result["authorization_servers"][0]
        parsed = urlparse(auth_server)
        assert parsed.path in ("", "/"), \
            f"authorization_servers must be root issuer, got path={parsed.path!r} (pre-inc_05 regression)"
        assert not parsed.query and not parsed.fragment, \
            "authorization_servers must not have query/fragment"

        # resource is the MCP resource URL
        assert result["resource"] == MCP_RESOURCE_URL

    @pytest.mark.asyncio
    async def test_openid_configuration_root_issuer(self):
        """PG-Claude AS metadata: issuer must be root, all endpoints on www."""
        from mcp_server.priority_guardian_claude.discovery_dupl import openid_configuration
        from mcp_server.priority_guardian_claude.config import OAUTH_ISSUER_BASE

        result = await openid_configuration()

        # issuer is root
        assert result["issuer"] == OAUTH_ISSUER_BASE

        # All endpoints on www (OAUTH_ISSUER_BASE)
        assert result["authorization_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["token_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["jwks_uri"].startswith(OAUTH_ISSUER_BASE)
        assert result["registration_endpoint"].startswith(OAUTH_ISSUER_BASE)

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_root_issuer(self):
        """
        PG-Claude oauth_authorization_server must match openid_configuration.

        Bug caught: editing one function but not the twin would pass CI without this.
        """
        from mcp_server.priority_guardian_claude.discovery_dupl import oauth_authorization_server
        from mcp_server.priority_guardian_claude.config import OAUTH_ISSUER_BASE

        result = await oauth_authorization_server()

        assert result["issuer"] == OAUTH_ISSUER_BASE
        assert result["authorization_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["token_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["jwks_uri"].startswith(OAUTH_ISSUER_BASE)
        assert result["registration_endpoint"].startswith(OAUTH_ISSUER_BASE)


class TestMindSortClaudeDiscoveryShape:
    """
    Tests for MindSort Claude MCP server discovery (Shape #3).

    Same requirements as PG-Claude: root issuer for Claude compatibility.
    """

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_root_issuer(self):
        """
        MindSort-Claude PRM: authorization_servers must be root issuer.

        Bug caught: pre-inc_05 used path-qualified authorization_servers
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.mindsort_claude.config import (
            MCP_RESOURCE_URL,
            OAUTH_ISSUER_BASE,
        )

        result = await oauth_protected_resource()

        # authorization_servers MUST be root issuer
        assert result["authorization_servers"] == [OAUTH_ISSUER_BASE]

        # REGRESSION GUARD: must be root (no path)
        auth_server = result["authorization_servers"][0]
        parsed = urlparse(auth_server)
        assert parsed.path in ("", "/"), \
            f"authorization_servers must be root issuer, got path={parsed.path!r}"

        # resource is the MCP resource URL
        assert result["resource"] == MCP_RESOURCE_URL

    @pytest.mark.asyncio
    async def test_openid_configuration_root_issuer(self):
        """MindSort-Claude AS metadata: issuer must be root."""
        from mcp_server.mindsort_claude.discovery_dupl import openid_configuration
        from mcp_server.mindsort_claude.config import CLARITY_ISSUER

        result = await openid_configuration()

        # issuer is root
        assert result["issuer"] == CLARITY_ISSUER

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_root_issuer(self):
        """
        MindSort-Claude oauth_authorization_server must match openid_configuration.

        Bug caught: editing one function but not the twin would pass CI without this.
        """
        from mcp_server.mindsort_claude.discovery_dupl import oauth_authorization_server
        from mcp_server.mindsort_claude.config import CLARITY_ISSUER, OAUTH_ISSUER_BASE

        result = await oauth_authorization_server()

        # issuer is root
        assert result["issuer"] == CLARITY_ISSUER

        # All endpoints on www (OAUTH_ISSUER_BASE) — same assertions as PG-Claude
        assert result["authorization_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["token_endpoint"].startswith(OAUTH_ISSUER_BASE)
        assert result["jwks_uri"].startswith(OAUTH_ISSUER_BASE)
        assert result["registration_endpoint"].startswith(OAUTH_ISSUER_BASE)


# =============================================================================
# Backend Discovery (root AS metadata)
# =============================================================================

class TestBackendRootDiscovery:
    """
    Tests for backend root AS metadata (served at /.well-known/*).

    The Claude servers point at this root discovery. It must:
    - Have issuer = OAUTH_ISSUER (settings)
    - Have all endpoints under /oauth/pg/*
    """

    @pytest.mark.asyncio
    async def test_backend_openid_configuration(self):
        """Backend root discovery: issuer must be settings.OAUTH_ISSUER."""
        from backend.core.oauth_provider.discovery import _authorization_server_metadata
        from backend.core.config import settings

        result = _authorization_server_metadata()

        assert result["issuer"] == settings.OAUTH_ISSUER
        assert result["authorization_endpoint"] == f"{settings.OAUTH_ISSUER}/oauth/pg/authorize"
        assert result["token_endpoint"] == f"{settings.OAUTH_ISSUER}/oauth/pg/token"
        assert result["jwks_uri"] == f"{settings.OAUTH_ISSUER}/oauth/pg/jwks"
        assert result["registration_endpoint"] == f"{settings.OAUTH_ISSUER}/oauth/pg/register"


class TestBackendMindSortDiscovery:
    """
    Tests for backend MindSort-specific AS metadata (served at /oauth/mindsort/.well-known/*).

    MindSort-OpenAI points at this. Endpoints must be under /oauth/mindsort/*.
    """

    @pytest.mark.asyncio
    async def test_mindsort_authorization_server_metadata(self):
        """MindSort backend discovery: endpoints under /oauth/mindsort/*."""
        from backend.core.oauth_provider.mindsort_discovery import _mindsort_authorization_server_metadata
        from backend.core.config import settings

        result = _mindsort_authorization_server_metadata()

        # issuer is root (not path-qualified)
        assert result["issuer"] == settings.OAUTH_ISSUER

        # All endpoints under /oauth/mindsort/
        assert "/oauth/mindsort/authorize" in result["authorization_endpoint"]
        assert "/oauth/mindsort/token" in result["token_endpoint"]
        assert "/oauth/mindsort/jwks" in result["jwks_uri"]
        assert "/oauth/mindsort/register" in result["registration_endpoint"]


# =============================================================================
# Cross-Cutting Invariants (all discovery documents)
# =============================================================================

class TestCrossCuttingInvariants:
    """
    Invariants that must hold for ALL OAuth discovery documents.

    - code_challenge_methods_supported == ["S256"] (never plain)
    - response_types_supported == ["code"]
    - grant_types_supported includes authorization_code + refresh_token

    Bug caught: Claude refuses to connect if S256 is not advertised.
    Security: OAuth_Hard_Requirements.md §9 forbids plain.
    """

    @pytest.mark.asyncio
    async def test_all_discovery_s256_only(self):
        """
        All AS metadata documents must advertise code_challenge_methods_supported = ["S256"].

        Claude refuses without S256. OAuth_Hard_Requirements.md §9 forbids plain.
        """
        from mcp_server.priority_guardian.discovery import openid_configuration as pg_oidc
        from mcp_server.clarity.discovery import openid_configuration as clarity_oidc
        from mcp_server.priority_guardian_claude.discovery_dupl import openid_configuration as pg_claude_oidc
        from mcp_server.mindsort_claude.discovery_dupl import openid_configuration as mindsort_claude_oidc
        from backend.core.oauth_provider.discovery import _authorization_server_metadata as backend_root
        from backend.core.oauth_provider.mindsort_discovery import _mindsort_authorization_server_metadata as backend_mindsort

        all_docs = [
            ("PG-OpenAI", await pg_oidc()),
            ("MindSort-OpenAI", await clarity_oidc()),
            ("PG-Claude", await pg_claude_oidc()),
            ("MindSort-Claude", await mindsort_claude_oidc()),
            ("Backend-Root", backend_root()),
            ("Backend-MindSort", backend_mindsort()),
        ]

        for name, doc in all_docs:
            methods = doc.get("code_challenge_methods_supported", [])
            assert methods == ["S256"], \
                f"{name}: code_challenge_methods_supported must be ['S256'], got {methods}"

    @pytest.mark.asyncio
    async def test_all_discovery_response_types_code_only(self):
        """All AS metadata documents must advertise response_types_supported = ["code"]."""
        from mcp_server.priority_guardian.discovery import openid_configuration as pg_oidc
        from mcp_server.clarity.discovery import openid_configuration as clarity_oidc
        from mcp_server.priority_guardian_claude.discovery_dupl import openid_configuration as pg_claude_oidc
        from mcp_server.mindsort_claude.discovery_dupl import openid_configuration as mindsort_claude_oidc
        from backend.core.oauth_provider.discovery import _authorization_server_metadata as backend_root
        from backend.core.oauth_provider.mindsort_discovery import _mindsort_authorization_server_metadata as backend_mindsort

        all_docs = [
            ("PG-OpenAI", await pg_oidc()),
            ("MindSort-OpenAI", await clarity_oidc()),
            ("PG-Claude", await pg_claude_oidc()),
            ("MindSort-Claude", await mindsort_claude_oidc()),
            ("Backend-Root", backend_root()),
            ("Backend-MindSort", backend_mindsort()),
        ]

        for name, doc in all_docs:
            types = doc.get("response_types_supported", [])
            assert types == ["code"], \
                f"{name}: response_types_supported must be ['code'], got {types}"

    @pytest.mark.asyncio
    async def test_all_discovery_grant_types(self):
        """All AS metadata documents must support authorization_code + refresh_token."""
        from mcp_server.priority_guardian.discovery import openid_configuration as pg_oidc
        from mcp_server.clarity.discovery import openid_configuration as clarity_oidc
        from mcp_server.priority_guardian_claude.discovery_dupl import openid_configuration as pg_claude_oidc
        from mcp_server.mindsort_claude.discovery_dupl import openid_configuration as mindsort_claude_oidc
        from backend.core.oauth_provider.discovery import _authorization_server_metadata as backend_root
        from backend.core.oauth_provider.mindsort_discovery import _mindsort_authorization_server_metadata as backend_mindsort

        all_docs = [
            ("PG-OpenAI", await pg_oidc()),
            ("MindSort-OpenAI", await clarity_oidc()),
            ("PG-Claude", await pg_claude_oidc()),
            ("MindSort-Claude", await mindsort_claude_oidc()),
            ("Backend-Root", backend_root()),
            ("Backend-MindSort", backend_mindsort()),
        ]

        for name, doc in all_docs:
            grants = set(doc.get("grant_types_supported", []))
            expected = {"authorization_code", "refresh_token"}
            assert grants == expected, \
                f"{name}: grant_types_supported must be exactly {expected}, got {grants}"


# =============================================================================
# PRM Resource Invariants
# =============================================================================

class TestPRMResourceInvariants:
    """
    Protected Resource Metadata resource field must match configured MCP_RESOURCE_URL.
    """

    @pytest.mark.asyncio
    async def test_pg_openai_prm_resource(self):
        """PG-OpenAI PRM resource == configured MCP_RESOURCE_URL."""
        from mcp_server.priority_guardian.discovery import oauth_protected_resource
        from mcp_server.priority_guardian.config import MCP_RESOURCE_URL

        result = await oauth_protected_resource()
        assert result["resource"] == MCP_RESOURCE_URL

    @pytest.mark.asyncio
    async def test_clarity_openai_prm_resource(self):
        """MindSort-OpenAI PRM resource == configured MCP_SERVER_URL/mcp."""
        from mcp_server.clarity.discovery import oauth_protected_resource
        from mcp_server.clarity.config import MCP_SERVER_URL

        result = await oauth_protected_resource()
        assert result["resource"] == f"{MCP_SERVER_URL}/mcp"

    @pytest.mark.asyncio
    async def test_pg_claude_prm_resource(self):
        """PG-Claude PRM resource == configured MCP_RESOURCE_URL."""
        from mcp_server.priority_guardian_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.priority_guardian_claude.config import MCP_RESOURCE_URL

        result = await oauth_protected_resource()
        assert result["resource"] == MCP_RESOURCE_URL

    @pytest.mark.asyncio
    async def test_mindsort_claude_prm_resource(self):
        """MindSort-Claude PRM resource == configured MCP_RESOURCE_URL."""
        from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource
        from mcp_server.mindsort_claude.config import MCP_RESOURCE_URL

        result = await oauth_protected_resource()
        assert result["resource"] == MCP_RESOURCE_URL


# =============================================================================
# Mount-Coherence Checks (cross-service invariants)
# =============================================================================

def _get_backend_well_known_mounts() -> set[str]:
    """
    Introspect the backend router to find all path prefixes that have .well-known mounts.

    This replaces a hardcoded set to ensure the test fails if someone removes
    a discovery router mount from the backend.

    Returns:
        Set of path prefixes (e.g., {"", "/oauth/mindsort"}) where .well-known routes exist.
    """
    from backend.core.routers.oauth_provider_router import router

    mounts = set()
    for route in router.routes:
        if hasattr(route, 'path') and '.well-known' in route.path:
            path = route.path
            # Extract prefix before /.well-known
            # e.g., "/.well-known/openid-configuration" → ""
            # e.g., "/oauth/mindsort/.well-known/oauth-authorization-server" → "/oauth/mindsort"
            well_known_idx = path.find('/.well-known')
            if well_known_idx >= 0:
                prefix = path[:well_known_idx]
                mounts.add(prefix)

    return mounts


class TestMountCoherence:
    """
    Verify that paths advertised in MCP server discovery have corresponding
    backend .well-known mounts.

    This catches the scenario where an MCP server advertises /oauth/pg in
    authorization_servers but the backend has no /oauth/pg/.well-known/* mount
    (only / and /oauth/mindsort have .well-known sub-mounts).

    Bug this would catch: clarity config set to /oauth/pg → ChatGPT follows
    authorization_servers → 404 on /oauth/pg/.well-known/oauth-authorization-server.

    NOTE: These tests use production-shaped env values via monkeypatch + module
    reload. They verify that the CODE correctly propagates production values to
    discovery endpoints and that those paths have backend mounts. They do NOT
    verify that production Render env vars are correctly set — that requires
    the live suite.
    """

    @pytest.fixture
    def backend_well_known_mounts(self) -> set[str]:
        """Introspect actual backend router for .well-known mount prefixes."""
        return _get_backend_well_known_mounts()

    def test_mindsort_openai_authorization_servers_has_backend_mount(self, monkeypatch, backend_well_known_mounts):
        """
        MindSort-OpenAI with production env: authorization_servers path must have
        a backend .well-known mount.

        Uses production-shaped env values to verify the code correctly propagates
        /oauth/mindsort (which has a backend mount) vs /oauth/pg (which does not).
        """
        import sys

        # Set production-like env BEFORE importing
        # Uses canonical URLs from doc/CANONICAL_MCP_URLS.md
        monkeypatch.setenv("CLARITY_OAUTH_ISSUER_URL", "https://www.priority-guard.com/oauth/mindsort")
        monkeypatch.setenv("CLARITY_ISSUER", "https://www.priority-guard.com")
        monkeypatch.setenv("CLARITY_MCP_SERVER_URL", "https://mindsort.priority-guard.com")

        # Remove cached modules to force re-import with new env
        modules_to_reload = [
            "mcp_server.clarity.config",
            "mcp_server.clarity.discovery",
        ]
        for mod in modules_to_reload:
            if mod in sys.modules:
                del sys.modules[mod]

        try:
            from mcp_server.clarity.config import OAUTH_ISSUER_URL

            # Verify production value was actually loaded (catch wrong env var names)
            assert OAUTH_ISSUER_URL == "https://www.priority-guard.com/oauth/mindsort", \
                f"OAUTH_ISSUER_URL not production-shaped: {OAUTH_ISSUER_URL}"

            # Extract path from OAUTH_ISSUER_URL (e.g., /oauth/mindsort from
            # https://www.priority-guard.com/oauth/mindsort)
            parsed = urlparse(OAUTH_ISSUER_URL)
            advertised_path = parsed.path.rstrip("/")

            assert advertised_path in backend_well_known_mounts, (
                f"MindSort-OpenAI advertises authorization_servers path '{advertised_path}' "
                f"but backend only mounts .well-known at: {backend_well_known_mounts}. "
                f"This would cause 404 when ChatGPT follows the discovery chain. "
                f"Either fix CLARITY_OAUTH_ISSUER_URL or add the backend mount."
            )
        finally:
            # Clean up: remove modules so later tests get fresh imports
            for mod in modules_to_reload:
                if mod in sys.modules:
                    del sys.modules[mod]

    def test_claude_servers_authorization_servers_has_backend_mount(self, monkeypatch, backend_well_known_mounts):
        """
        Claude servers use root authorization_servers, which has a backend mount.

        Uses production-shaped env values to verify Claude servers correctly
        advertise root issuer (no path).
        """
        import sys

        # Set production-like env for PG-Claude (uses PG_CLAUDE_* prefix)
        monkeypatch.setenv("PG_CLAUDE_OAUTH_ISSUER_BASE", "https://www.priority-guard.com")
        monkeypatch.setenv("PG_CLAUDE_OAUTH_ISSUER_URL", "https://www.priority-guard.com/oauth/pg")
        monkeypatch.setenv("PG_CLAUDE_MCP_SERVER_URL", "https://mcp.priority-guard.com")
        monkeypatch.setenv("PG_CLAUDE_MCP_RESOURCE_URL", "https://mcp.priority-guard.com/mcp")

        # Set production-like env for MindSort-Claude (uses CLARITY_CLAUDE_* prefix)
        monkeypatch.setenv("CLARITY_CLAUDE_OAUTH_ISSUER_BASE", "https://www.priority-guard.com")
        monkeypatch.setenv("CLARITY_CLAUDE_OAUTH_ISSUER_URL", "https://www.priority-guard.com/oauth/pg")
        monkeypatch.setenv("CLARITY_CLAUDE_ISSUER", "https://www.priority-guard.com")
        monkeypatch.setenv("CLARITY_CLAUDE_MCP_SERVER_URL", "https://mindsort-mcp.priority-guard.com")
        monkeypatch.setenv("CLARITY_CLAUDE_MCP_RESOURCE_URL", "https://mindsort-mcp.priority-guard.com/mcp")
        # MindSort-Claude also needs CORS in production mode
        monkeypatch.setenv("CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS", "https://claude.ai")

        # Remove cached modules to force re-import with new env
        modules_to_reload = [
            "mcp_server.priority_guardian_claude.config",
            "mcp_server.mindsort_claude.config",
        ]
        for mod in modules_to_reload:
            if mod in sys.modules:
                del sys.modules[mod]

        try:
            from mcp_server.priority_guardian_claude.config import OAUTH_ISSUER_BASE as PG_OAUTH_BASE
            from mcp_server.mindsort_claude.config import OAUTH_ISSUER_BASE as MS_OAUTH_BASE

            # Verify production values were actually loaded (catch wrong env var names)
            assert PG_OAUTH_BASE == "https://www.priority-guard.com", \
                f"PG-Claude OAUTH_ISSUER_BASE not production-shaped: {PG_OAUTH_BASE}"
            assert MS_OAUTH_BASE == "https://www.priority-guard.com", \
                f"MindSort-Claude OAUTH_ISSUER_BASE not production-shaped: {MS_OAUTH_BASE}"

            for name, issuer_base in [("PG-Claude", PG_OAUTH_BASE), ("MindSort-Claude", MS_OAUTH_BASE)]:
                parsed = urlparse(issuer_base)
                advertised_path = parsed.path.rstrip("/")

                # Claude servers must use root (empty path)
                assert advertised_path in ("", "/"), (
                    f"{name} authorization_servers has path '{advertised_path}' "
                    f"but Claude requires root issuer (no path). "
                    f"See ADR_005 Shape #3."
                )

                # Root has a backend mount (introspected from actual router)
                assert "" in backend_well_known_mounts, \
                    f"Root path not found in backend mounts: {backend_well_known_mounts}"
        finally:
            # Clean up: remove modules so later tests get fresh imports
            for mod in modules_to_reload:
                if mod in sys.modules:
                    del sys.modules[mod]


# =============================================================================
# Production-Shaped Env Tests
# =============================================================================

class TestProductionEnvShapes:
    """
    Tests that verify discovery shapes with production-like env values.

    These tests use sys.modules purging to re-evaluate config modules with
    production env vars set. This catches bugs where code works with dev
    defaults but would fail with production values.

    NOTE: These tests verify CODE BEHAVIOR with production-shaped values.
    They do NOT verify that production Render env vars are correctly set —
    that requires the live suite (tests/integration/oauth_discovery/).

    Canonical URLs: see doc/CANONICAL_MCP_URLS.md
    """

    @pytest.mark.asyncio
    async def test_mindsort_openai_production_shape(self, monkeypatch):
        """
        MindSort-OpenAI with production env must advertise /oauth/mindsort chain.

        This catches: dev default /oauth/pg working but production /oauth/mindsort
        being broken due to code bug.
        """
        import sys

        # Set production-like env BEFORE importing
        # Canonical URL: mindsort.priority-guard.com (see doc/CANONICAL_MCP_URLS.md)
        monkeypatch.setenv("CLARITY_OAUTH_ISSUER_URL", "https://www.priority-guard.com/oauth/mindsort")
        monkeypatch.setenv("CLARITY_ISSUER", "https://www.priority-guard.com")
        monkeypatch.setenv("CLARITY_MCP_SERVER_URL", "https://mindsort.priority-guard.com")

        # Remove cached modules to force re-import with new env
        modules_to_reload = [
            "mcp_server.clarity.config",
            "mcp_server.clarity.discovery",
        ]
        for mod in modules_to_reload:
            if mod in sys.modules:
                del sys.modules[mod]

        try:
            # Now import with production env
            from mcp_server.clarity.config import OAUTH_ISSUER_URL
            from mcp_server.clarity.discovery import oauth_protected_resource, openid_configuration

            # Verify production values were loaded (strict equality, not substring)
            assert OAUTH_ISSUER_URL == "https://www.priority-guard.com/oauth/mindsort", \
                f"Expected exact production path, got {OAUTH_ISSUER_URL}"

            # Verify discovery propagates correctly
            prm = await oauth_protected_resource()
            assert prm["authorization_servers"][0] == "https://www.priority-guard.com/oauth/mindsort", \
                f"PRM authorization_servers mismatch: {prm['authorization_servers']}"

            oidc = await openid_configuration()
            assert "/oauth/mindsort/" in oidc["token_endpoint"], \
                f"token_endpoint should be under /oauth/mindsort/"
        finally:
            # Clean up: remove modules so later tests get fresh imports
            for mod in modules_to_reload:
                if mod in sys.modules:
                    del sys.modules[mod]

    @pytest.mark.asyncio
    async def test_pg_claude_production_shape(self, monkeypatch):
        """
        PG-Claude with production env must advertise root issuer.
        """
        import sys

        monkeypatch.setenv("PG_CLAUDE_OAUTH_ISSUER_BASE", "https://www.priority-guard.com")
        monkeypatch.setenv("PG_CLAUDE_OAUTH_ISSUER_URL", "https://www.priority-guard.com/oauth/pg")
        monkeypatch.setenv("PG_CLAUDE_MCP_SERVER_URL", "https://mcp.priority-guard.com")
        monkeypatch.setenv("PG_CLAUDE_MCP_RESOURCE_URL", "https://mcp.priority-guard.com/mcp")

        modules_to_reload = [
            "mcp_server.priority_guardian_claude.config",
            "mcp_server.priority_guardian_claude.discovery_dupl",
        ]
        for mod in modules_to_reload:
            if mod in sys.modules:
                del sys.modules[mod]

        try:
            from mcp_server.priority_guardian_claude.config import OAUTH_ISSUER_BASE
            from mcp_server.priority_guardian_claude.discovery_dupl import oauth_protected_resource

            # Verify production values (strict equality)
            assert OAUTH_ISSUER_BASE == "https://www.priority-guard.com", \
                f"PG-Claude OAUTH_ISSUER_BASE not production: {OAUTH_ISSUER_BASE}"

            # Verify discovery propagates correctly
            prm = await oauth_protected_resource()
            auth_server = prm["authorization_servers"][0]

            # Must be exactly root issuer
            assert auth_server == "https://www.priority-guard.com", \
                f"Claude authorization_servers must be root issuer, got {auth_server}"
        finally:
            # Clean up: remove modules so later tests get fresh imports
            for mod in modules_to_reload:
                if mod in sys.modules:
                    del sys.modules[mod]

    @pytest.mark.asyncio
    async def test_mindsort_claude_production_shape(self, monkeypatch):
        """
        MindSort-Claude with production env must advertise root issuer.

        Uses CLARITY_CLAUDE_* env vars (not MINDSORT_CLAUDE_*).
        """
        import sys

        # MindSort-Claude uses CLARITY_CLAUDE_* prefix
        monkeypatch.setenv("CLARITY_CLAUDE_OAUTH_ISSUER_BASE", "https://www.priority-guard.com")
        monkeypatch.setenv("CLARITY_CLAUDE_OAUTH_ISSUER_URL", "https://www.priority-guard.com/oauth/pg")
        monkeypatch.setenv("CLARITY_CLAUDE_ISSUER", "https://www.priority-guard.com")
        monkeypatch.setenv("CLARITY_CLAUDE_MCP_SERVER_URL", "https://mindsort-mcp.priority-guard.com")
        monkeypatch.setenv("CLARITY_CLAUDE_MCP_RESOURCE_URL", "https://mindsort-mcp.priority-guard.com/mcp")
        monkeypatch.setenv("CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS", "https://claude.ai")

        modules_to_reload = [
            "mcp_server.mindsort_claude.config",
            "mcp_server.mindsort_claude.discovery_dupl",
        ]
        for mod in modules_to_reload:
            if mod in sys.modules:
                del sys.modules[mod]

        try:
            from mcp_server.mindsort_claude.config import OAUTH_ISSUER_BASE, MCP_RESOURCE_URL
            from mcp_server.mindsort_claude.discovery_dupl import oauth_protected_resource

            # Verify production values (strict equality)
            assert OAUTH_ISSUER_BASE == "https://www.priority-guard.com", \
                f"MindSort-Claude OAUTH_ISSUER_BASE not production: {OAUTH_ISSUER_BASE}"
            assert MCP_RESOURCE_URL == "https://mindsort-mcp.priority-guard.com/mcp", \
                f"MindSort-Claude MCP_RESOURCE_URL not production: {MCP_RESOURCE_URL}"

            # Verify discovery propagates correctly
            prm = await oauth_protected_resource()
            auth_server = prm["authorization_servers"][0]

            # Must be exactly root issuer
            assert auth_server == "https://www.priority-guard.com", \
                f"Claude authorization_servers must be root issuer, got {auth_server}"

            # Resource must match canonical URL
            assert prm["resource"] == "https://mindsort-mcp.priority-guard.com/mcp", \
                f"PRM resource mismatch: {prm['resource']}"
        finally:
            # Clean up: remove modules so later tests get fresh imports
            for mod in modules_to_reload:
                if mod in sys.modules:
                    del sys.modules[mod]
