# (duplicate) — exists only because it imports platform-specific config.
# Mirrors mcp_server/clarity/mcp_auth.py. Maintain alongside; consolidate only on demonstrated churn.
#
# WARNING — PROCESS-WIDE SIDE EFFECT:
# Importing this module MUTATES mcp_server.clarity.mcp_auth's module-level globals
# (TOOL_SCOPES, CLARITY_ISSUER, etc.) to MindSort-Claude values. This rebinding is
# intentional for production (single-app process), but creates a test hazard:
#
#   If a test session imports this shim (or server_dupl, which imports it transitively)
#   AND later runs tests that import clarity.mcp_auth directly, those clarity tests
#   will see MindSort-Claude's rebound values, not clarity's originals.
#
# Known test imports (as of 2026-07-04):
#   tests/unit/mcp_claude_mindsort/test_scaffold.py:53,64 — server_dupl (transitive)
#   tests/unit/mcp_claude_mindsort/test_scaffold.py:168 — mcp_auth_dupl (direct)
#
# Safe pattern: scope invariant tests import only config modules, never auth modules.
# If cross-contamination becomes a problem, isolate MindSort-Claude tests in a
# separate pytest session (--forked or CI matrix split).
#
# ============================================================================
# PERSISTENCE NAMESPACE CONTRACT (2026-07-05 — incident-driven documentation)
# ============================================================================
# The following clarity/config.py variables are NOT rebound by this shim:
#   - CLARITY_BACKEND_URL (used by persistence.py)
#   - INTERNAL_API_SECRET (used by persistence.py)
#
# These must be set explicitly in the MindSort-Claude Render env. If missing,
# they fall back to clarity's defaults (localhost), causing silent persistence
# failures. The localhost guard in clarity/config.py now fails at boot in
# production if CLARITY_BACKEND_URL contains localhost — but the env var must
# still be set. See clarity/config.py comment block for the full incident story.
#
# Env vars required for MindSort-Claude persistence:
#   CLARITY_BACKEND_URL = https://www.priority-guard.com
#   INTERNAL_API_SECRET = <matches backend>
#
# ============================================================================
# EXPLICITLY NOT REBOUND (architecture decision — do not add)
# ============================================================================
# The following config.py variables are NOT rebound by this shim AND MUST NOT BE:
#   - OAUTH_ISSUER_URL (used by discovery.py)
#   - SCOPES_SUPPORTED (used by discovery.py)
#
# Rationale: MindSort-Claude uses its own discovery_dupl.py importing from its own
# config.py — discovery is DELIBERATELY DUPLICATED per the _dupl convention, not
# shared. clarity.mcp_auth never reads OAUTH_ISSUER_URL or SCOPES_SUPPORTED, so
# rebinding them would be dead code. Worse, adding them to REBOUND_GLOBALS would
# desynchronize the tuple from the actual _shared.* assignments, causing the AST
# and drift meta-tests to fail by design.
#
# If a future reviewer suggests adding these: re-read this comment and the
# discovery_dupl.py/config.py separation. The shim rebinds AUTH globals because
# auth is shared; discovery is intentionally per-service.
# ============================================================================

import mcp_server.clarity.mcp_auth as _shared

from mcp_server.mindsort_claude.config import (
    CLARITY_JWKS_URL,
    CLARITY_ISSUER,
    CLARITY_AUDIENCE,
    MCP_SERVER_URL,
    MCP_RESOURCE_URL,
    TOOL_SCOPES,
    TOKEN_EXPIRY_GRACE_SECONDS,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
)

# Rebind config-dependent module globals to Claude platform values
# NOTE: REBOUND_GLOBALS is the authoritative list of what this shim mutates.
# The test fixture (restore_mcp_auth_globals) MUST save/restore all of these.
# If you add a rebinding below, add its name to REBOUND_GLOBALS.
REBOUND_GLOBALS = (
    "CLARITY_JWKS_URL",
    "CLARITY_ISSUER",
    "CLARITY_AUDIENCE",
    "MCP_SERVER_URL",
    "MCP_RESOURCE_URL",
    "TOOL_SCOPES",
    "TOKEN_EXPIRY_GRACE_SECONDS",
    "JWKS_CACHE_TTL_SECONDS",
    "JWKS_MAX_STALE_SECONDS",
    "JWKS_FETCH_TIMEOUT_SECONDS",
)

_shared.CLARITY_JWKS_URL = CLARITY_JWKS_URL
_shared.CLARITY_ISSUER = CLARITY_ISSUER
_shared.CLARITY_AUDIENCE = CLARITY_AUDIENCE
_shared.MCP_SERVER_URL = MCP_SERVER_URL
_shared.MCP_RESOURCE_URL = MCP_RESOURCE_URL
_shared.TOOL_SCOPES = TOOL_SCOPES
_shared.TOKEN_EXPIRY_GRACE_SECONDS = TOKEN_EXPIRY_GRACE_SECONDS
_shared.JWKS_CACHE_TTL_SECONDS = JWKS_CACHE_TTL_SECONDS
_shared.JWKS_MAX_STALE_SECONDS = JWKS_MAX_STALE_SECONDS
_shared.JWKS_FETCH_TIMEOUT_SECONDS = JWKS_FETCH_TIMEOUT_SECONDS

# Re-export everything callers need
from mcp_server.clarity.mcp_auth import (  # noqa: E402, F401
    authenticate_request,
    cleanup_jwks_cache,
    build_unauthorized_meta,
    build_forbidden_meta,
    UnauthorizedError,
    InsufficientScopeError,
    JWKSCache,
)
