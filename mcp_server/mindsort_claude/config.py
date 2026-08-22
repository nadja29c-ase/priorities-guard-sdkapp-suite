"""
Configuration for MindSort Claude MCP Server.

Centralizes all MCP-specific settings including JWT validation,
JWKS fetching, and OAuth client configuration.

Uses /oauth/pg/* endpoints (shared Priority Guardian OAuth provider).

# ============================================================================
# Required Render Environment Variables — MindSort-Claude is LIVE IN PRODUCTION
# (framing corrected 2026-07-31: this previously read "for future deployment")
# ============================================================================
# CLARITY_CLAUDE_MCP_SERVER_URL   = <deployed Claude origin, NO /mcp>   e.g. https://mindsort-mcp.priority-guard.com
# CLARITY_CLAUDE_MCP_RESOURCE_URL = <origin>/mcp                        (derives automatically; only set if overriding)
# CLARITY_CLAUDE_OAUTH_ISSUER_URL = https://www.priority-guard.com/oauth/pg
# CLARITY_CLAUDE_BACKEND_URL      = https://www.priority-guard.com
# CLARITY_CLAUDE_INTERNAL_API_SECRET = <matches backend INTERNAL_API_SECRET>
# CLARITY_CLAUDE_JWKS_URL         = https://www.priority-guard.com/oauth/pg/jwks
# CLARITY_CLAUDE_ISSUER           = https://www.priority-guard.com
# CLARITY_CLAUDE_AUDIENCE         = https://mindsort-mcp.priority-guard.com/mcp  # resource-shaped, NOT issuer
# CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS = <comma-separated list if needed>
# ENV = production
"""

import os
from typing import Optional
from urllib.parse import urlparse


# ============================================================================
# Environment Detection
# ============================================================================

ENV = os.getenv("ENV", "dev")

# Known ENV values — fail fast on unknown to prevent production guards being silently bypassed
# Production values trigger required-env guards; dev/test values use defaults.
_PRODUCTION_ENV_VALUES = {"production", "prod", "staging"}
_DEV_ENV_VALUES = {"dev", "development", "local", "test", "ci"}
_KNOWN_ENV_VALUES = _PRODUCTION_ENV_VALUES | _DEV_ENV_VALUES


def _is_production_env(env: str) -> bool:
    """Return True if env is a production-like environment.

    Canonical predicate — use this everywhere instead of inline tuples.
    Includes "prod" alias that PG uses, preventing ENV=prod from bypassing guards.
    """
    return env in _PRODUCTION_ENV_VALUES


# Fail-fast: raise on unknown ENV to prevent guards being bypassed
# Without this, a typo like ENV=produciton silently runs in non-production mode,
# letting localhost defaults leak into what the operator thinks is production.
# Note: Case and whitespace variants (ENV=Production, ENV=" production ") intentionally
# fail here rather than being normalized — maximally explicit, no silent coercion.
if ENV not in _KNOWN_ENV_VALUES:
    raise RuntimeError(
        f"Unknown ENV value {ENV!r}. "
        f"Known values: {sorted(_KNOWN_ENV_VALUES)}. "
        f"Refusing to start — this prevents production guards from being silently bypassed."
    )


# ============================================================================
# Helper Functions
# ============================================================================

def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get environment variable with optional default and requirement check.

    Args:
        key: Environment variable name
        default: Default value if not set (mutually exclusive with required=True)
        required: If True, raise in production/staging when not set

    Returns:
        Environment variable value, default, or None

    Raises:
        RuntimeError: If required=True and not set in production/staging
        AssertionError: If required=True and default is not None (config mistake)
    """
    # Catch config mistakes: required=True with a default makes no sense
    # (the default would always be used, so required check never triggers)
    assert not (required and default is not None), \
        f"get_env({key}): required=True is incompatible with default={default!r}"

    value = os.getenv(key, default)

    if required and value is None:
        if _is_production_env(ENV):
            raise RuntimeError(
                f"Required environment variable {key} not set. "
                f"This is required in {ENV} environment."
            )

    return value


# ============================================================================
# JWT Validation Settings
# ============================================================================

# JWKS URL - uses /oauth/pg/ (Priority Guardian shared OAuth)
CLARITY_JWKS_URL = get_env(
    "CLARITY_CLAUDE_JWKS_URL",
    default="http://localhost:8000/oauth/pg/jwks"
)

# Expected JWT issuer (iss claim)
# NOTE: Uses domain-only issuer to match existing Focused pattern.
# Path-qualified issuer (e.g., .../oauth/pg) is a future hardening task.
CLARITY_ISSUER = get_env(
    "CLARITY_CLAUDE_ISSUER",
    default="https://www.priority-guard.com"
)

# Expected JWT audience (aud claim)
# RATIONALE: The audience identifies the intended recipient of the token.
# This MUST match what the OAuth provider (/oauth/pg/token) issues in the 'aud' claim.
#
# ✅ CURRENT STATE (verified 2026-08-22): MindSort-Claude's audience config is
# CORRECT in production. §11 is CLOSED for this server.
#
#   CLARITY_CLAUDE_AUDIENCE = https://mindsort-mcp.priority-guard.com/mcp   <-- RESOURCE
#   MCP_RESOURCE_URL        = https://mindsort-mcp.priority-guard.com/mcp   (derived)
#
# Byte-equal. Verified TWO independent ways: the deployed Render value was read
# directly, AND _validate_audience_config() below refuses to boot in a production ENV
# unless the audience is explicitly set and byte-exactly equals the resource URL — so
# the service running at all is proof the values match. That guard is also why this
# cannot silently regress: an issuer-shaped value now fails boot rather than quietly
# disabling the audience layer.
#
# ⚠️ THE "BOTH CLAUDE SERVERS" CLAIM BELOW IS STALE — do not act on it. The blocks
# that follow are retained as history, in supersession order, newest first. Reading
# them as current will send you to "fix" a MindSort env var that is already correct.
#
# §11 SCOPE, as far as this file can establish it: PG-Claude only, and UNVERIFIED
# there. PG has NO equivalent _validate_audience_config boot guard, and PG_AUDIENCE
# still defaults to the issuer (priority_guardian_claude/config.py:125-128) — so the
# defect could be live on PG with nothing preventing it. That needs its own check
# against PG's deployed value; it is not established here, and "both servers" is now
# known to be wrong for at least one of the two.
#
# ---------------------------------------------------------------------------
# SUPERSEDED 2026-08-22 — was accurate when written; the env has since been fixed.
# ⚠️ FALSE CLAIM CORRECTED 2026-07-31. This block previously read:
#
#   "PRODUCTION SHAPE (verified 2026-07-04): In production, CLARITY_CLAUDE_AUDIENCE is
#    set to the resource URL (https://mindsort-mcp.priority-guard.com/mcp), NOT the
#    issuer URL. ... The code default should NOT be changed — production env
#    compensation is correct."
#
# PRODUCTION DOES NOT COMPENSATE. The deployed Render value read 2026-07-31 is:
#
#   CLARITY_CLAUDE_AUDIENCE = https://www.priority-guard.com      <-- the ISSUER
#   MCP_RESOURCE_URL        = https://mindsort-mcp.priority-guard.com/mcp
#
# Not byte-equal. So MindSort-Claude accepts issuer-audience tokens in production TODAY —
# the same defect previously attributed only to PG-Claude. The comment asserted a
# verification that was wrong, and because it was written as verified fact it was
# believed: it shaped an entire increment, framing MindSort's exposure as a latent hazard
# and PG-Claude's as the real one. Both Claude resource servers have it, live.
#
# [SUPERSEDED 2026-08-22: no longer true for MindSort. The env was corrected and the
#  boot guard added; the deployed value is now resource-shaped and byte-exact. The
#  lesson this block records — that a comment asserting a verification it never did
#  gets believed and shapes work — applies equally to this correction, which was
#  itself left stale for three weeks after the env was fixed.]
#
# SEVERITY, so this is not over-read: there is no live exploit. valid_audiences is
# [MCP_RESOURCE_URL, MCP_SERVER_URL, CLARITY_AUDIENCE] — the issuer is an EXTRA accepted
# audience, not the one real tokens carry. Production logs show every claude.ai flow
# carrying resource=https://mindsort-mcp.priority-guard.com/mcp, matching the first
# entry. Cross-app separation still holds because the per-tool SCOPE check separates the
# apps. What is dead is the audience layer, on both servers.
#
# DO NOT "fix" this by changing the code default. The correct fix is to set the Render
# env var to the resource URL, gated on confirming no outstanding issuer-audience tokens
# would break (§5 step 9 SQL, scoped to MindSort clients). Tracked as §11.
# [SUPERSEDED 2026-08-22: the env var HAS been set to the resource URL on MindSort, so
#  this instruction is already carried out here. §11's remaining scope is PG-Claude,
#  unverified — see the CURRENT STATE block at the top.]
#
# ---------------------------------------------------------------------------
# HISTORICAL — the paragraph below is retained for deployment history and is NO
# LONGER THE DESIGN INTENT. Corrected 2026-07-31. See
# doc/ADR/ADR_006_token_revocation_semantics.md and §11.
#
#   "Both Clarity and Focused MCP servers accept the same audience since they
#    share a single OAuth provider - scope-based access control (clarity.write
#    vs focused.write) determines which MCP server accepts which tokens."
#
# WHY IT IS NO LONGER THE INTENT:
#   1. It describes isolation resting on SCOPE rather than on resource-scoped
#      AUDIENCE binding. ADR_006 records that as the current posture and the
#      thing being closed, not as the target state — and the correction block
#      immediately above confirms it is exactly what production does today.
#   2. It is Focused-era. Focused is deprecated and its Render service suspended.
#   3. Accepting a shared audience is the §11 defect. [SUPERSEDED 2026-08-22: the
#      "confirmed live on BOTH Claude servers" claim here is stale — MindSort's
#      deployed audience is resource-shaped and boot-guarded. PG unverified.]
# ---------------------------------------------------------------------------
CLARITY_AUDIENCE = get_env(
    "CLARITY_CLAUDE_AUDIENCE",
    default="https://www.priority-guard.com"
)

# Token expiry grace period (seconds)
TOKEN_EXPIRY_GRACE_SECONDS = int(get_env(
    "TOKEN_EXPIRY_GRACE_SECONDS",
    default="30"
))

# JWKS cache settings
JWKS_CACHE_TTL_SECONDS = int(get_env(
    "JWKS_CACHE_TTL_SECONDS",
    default=str(24 * 3600)
))

JWKS_MAX_STALE_SECONDS = int(get_env(
    "JWKS_MAX_STALE_SECONDS",
    default=str(7 * 24 * 3600)
))

JWKS_FETCH_TIMEOUT_SECONDS = int(get_env(
    "JWKS_FETCH_TIMEOUT_SECONDS",
    default="5"
))


# ============================================================================
# Backend Configuration
# ============================================================================

BACKEND_URL = get_env(
    "CLARITY_CLAUDE_BACKEND_URL",
    default="http://localhost:8000"
).rstrip("/")

# Internal API secret for authenticated backend calls
# Must match INTERNAL_API_SECRET in backend config
# COUPLING: Empty string "" means "skip verification" in BOTH:
#   - MCP server (here): sends no X-Internal-API-Secret header
#   - Backend: accepts requests without the header when its secret is also ""
# This enables local dev without secrets. In prod, both must have matching values.
INTERNAL_API_SECRET = get_env(
    "CLARITY_CLAUDE_INTERNAL_API_SECRET",
    default=""  # Empty = dev mode (backend skips verification)
)


# ============================================================================
# OAuth Discovery Configuration
# ============================================================================

# MindSort Claude MCP Server public URL
# CRITICAL: This is an ORIGIN with NO /mcp path.
# discovery.py appends /mcp itself (resource = f"{MCP_SERVER_URL}/mcp"),
# and MCP_RESOURCE_URL derives as {MCP_SERVER_URL}/mcp.
# Putting /mcp in MCP_SERVER_URL produces https://domain/mcp/mcp and breaks
# the resource claim, the .well-known URLs, AND the ui.domain hash.
MCP_SERVER_URL = get_env(
    "CLARITY_CLAUDE_MCP_SERVER_URL",
    default="http://localhost:8003"
).rstrip("/")

# MCP Resource URL (the resource claim value)
# Defaults to {MCP_SERVER_URL}/mcp - only override if you need a different value
MCP_RESOURCE_URL = get_env(
    "CLARITY_CLAUDE_MCP_RESOURCE_URL",
    default=f"{MCP_SERVER_URL}/mcp"
)


# ============================================================================
# Boot guard — CLARITY_CLAUDE_AUDIENCE must be explicit and byte-exact
# ============================================================================
#
# WHY THIS EXISTS. This module already fails fast at boot on unknown ENV, on
# OAUTH_ISSUER_BASE path shape, on AS origin mismatch, on localhost-in-production, and
# on missing CORS origins — but CLARITY_CLAUDE_AUDIENCE silently fell back to an
# issuer-shaped default. That value participates directly in cross-app token isolation,
# so it was the least guarded of the consequential settings. The asymmetry was the defect.
#
# THIS IS A PATTERN, NOT A ONE-OFF. ADR_005 records the same failure class from the
# other direction: a production env-value regression on CLARITY_OAUTH_ISSUER_URL, which
# unit tests cannot catch because they exercise code shape rather than deployed values.
# Env-value regressions are caught by boot guards like this one and by the live
# discovery suite (`pytest -m live tests/integration/oauth_discovery/`).
#
# BYTE-EXACT, NO CANONICALIZATION — deliberately. No trailing-slash tolerance, no case
# folding, no percent-decoding. The runtime chain is:
#     PRM advertises `resource` -> client echoes `resource=` -> backend copies it into
#     `aud` -> PyJWT string-matches it
# PyJWT 2.10.1 compares `aud` by exact string equality (empirically verified: trailing
# slash, case and prefix variants are all rejected). A guard laxer than the validator is
# worse than no guard: it passes a config that then fails at runtime, while manufacturing
# confidence that the config was checked.
#
# Same-origin comparison was considered and REJECTED as insufficient: it would let
# https://host/pg satisfy a guard whose expected value is https://host/mindsort — the
# exact confusion this guard exists to prevent. Origin equality stops protecting the
# moment two apps share a host with path-based resource identifiers, which is this
# suite's topology.
#
# See doc/ADR/ADR_006_token_revocation_semantics.md for the audience/isolation posture.

def _validate_audience_config(
    env: str,
    audience_explicitly_set: bool,
    audience: Optional[str],
    resource_url: Optional[str],
) -> None:
    """
    Fail boot in production-like ENV unless the audience is explicit and byte-exact.

    Pure function, so tests can exercise every branch without importlib.reload and its
    module-global rebinding hazard (see mcp_auth_dupl's REBOUND_GLOBALS).

    Args:
        env: The resolved ENV value
        audience_explicitly_set: Whether CLARITY_CLAUDE_AUDIENCE was actually present in
            the environment. Read from os.getenv directly — the module-level value holds
            a default, so it cannot distinguish "set to the default" from "not set".
        audience: The effective audience value
        resource_url: The effective MCP_RESOURCE_URL

    Raises:
        RuntimeError: naming the variable, the expected value and the actual value
    """
    if not _is_production_env(env):
        return

    if not audience_explicitly_set:
        raise RuntimeError(
            "CLARITY_CLAUDE_AUDIENCE is not set. It must be set explicitly in "
            f"{env} — the code default is issuer-shaped and would silently disable "
            "cross-app audience isolation. "
            f"Expected it to equal CLARITY_CLAUDE_MCP_RESOURCE_URL ({resource_url!r}). "
            "Refusing to start."
        )

    if audience != resource_url:
        raise RuntimeError(
            "CLARITY_CLAUDE_AUDIENCE does not match CLARITY_CLAUDE_MCP_RESOURCE_URL. "
            "Comparison is byte-exact by design — PyJWT matches `aud` by exact string "
            "equality, so a laxer guard would pass a config that fails at runtime. "
            f"expected={resource_url!r} actual={audience!r} env={env!r}. "
            "Refusing to start."
        )


_validate_audience_config(
    env=ENV,
    audience_explicitly_set=os.getenv("CLARITY_CLAUDE_AUDIENCE") is not None,
    audience=CLARITY_AUDIENCE,
    resource_url=MCP_RESOURCE_URL,
)

# OAuth Authorization Server URL (uses /oauth/pg/)
# NOTE: This is the authorization server base URL for discovery, NOT the JWT 'iss' claim.
# - OAUTH_ISSUER_URL: http://localhost:8000/oauth/pg (authorization server endpoints)
# - CLARITY_ISSUER: https://www.priority-guard.com (JWT iss claim value)
# These differ because the OAuth provider uses a domain-only issuer in tokens.
OAUTH_ISSUER_URL = get_env(
    "CLARITY_CLAUDE_OAUTH_ISSUER_URL",
    default="http://localhost:8000/oauth/pg"
)

# Authorization server base URL (issuer identifier and authorization_servers reference)
# Must match backend's OAUTH_ISSUER env var exactly.
# Used for: issuer claim in AS metadata, authorization_servers in protected resource metadata.
# Do NOT derive from OAUTH_ISSUER_URL — define explicitly to avoid path-change fragility.
#
# NOTE: CLARITY_ISSUER (JWT iss validation) and OAUTH_ISSUER_BASE (discovery advertisement)
# hold the same production value (https://www.priority-guard.com) but serve different roles:
# - CLARITY_ISSUER: validates the 'iss' claim in incoming JWTs
# - OAUTH_ISSUER_BASE: advertised in oauth-protected-resource.authorization_servers
# Keep both explicit to prevent coupling bugs.
OAUTH_ISSUER_BASE = get_env(
    "CLARITY_CLAUDE_OAUTH_ISSUER_BASE",
    default="http://localhost:8000"
).rstrip("/")  # Normalize: remove trailing slash to ensure root comparison works

# Fail-fast: OAUTH_ISSUER_BASE must be a root issuer (no path, query, or fragment)
# A path like /oauth/pg would make authorization_servers non-root, breaking Claude discovery.
# The .rstrip("/") handles trailing slash; this rejects real paths.
_base_parsed = urlparse(OAUTH_ISSUER_BASE)
if _base_parsed.path not in ("", "/") or _base_parsed.query or _base_parsed.fragment:
    raise RuntimeError(
        f"CLARITY_CLAUDE_OAUTH_ISSUER_BASE must be a root issuer (no path, query, or fragment). "
        f"Got {OAUTH_ISSUER_BASE!r} with path={_base_parsed.path!r}, "
        f"query={_base_parsed.query!r}, fragment={_base_parsed.fragment!r}."
    )

# Fail-fast: OAUTH_ISSUER_URL must share the same origin as OAUTH_ISSUER_BASE (RFC 8414)
# Without this check, discovery could return issuer=www but token_endpoint=api,
# which causes silent OAuth failures in Claude.
# Note: startswith() is insufficient — "https://www.example.com.evil.com" starts with
# "https://www.example.com" but has a completely different origin.
# _base_parsed already defined above (shape guard); only need _url_parsed here.
_url_parsed = urlparse(OAUTH_ISSUER_URL)

if (_base_parsed.scheme, _base_parsed.netloc) != (_url_parsed.scheme, _url_parsed.netloc):
    raise RuntimeError(
        f"CLARITY_CLAUDE_OAUTH_ISSUER_URL must share the same origin as CLARITY_CLAUDE_OAUTH_ISSUER_BASE (RFC 8414). "
        f"Got CLARITY_CLAUDE_OAUTH_ISSUER_BASE={OAUTH_ISSUER_BASE!r} (origin: {_base_parsed.scheme}://{_base_parsed.netloc}), "
        f"CLARITY_CLAUDE_OAUTH_ISSUER_URL={OAUTH_ISSUER_URL!r} (origin: {_url_parsed.scheme}://{_url_parsed.netloc})."
    )

# Fail-fast: OAUTH_ISSUER_BASE must not contain localhost in production
# Uses canonical _is_production_env() predicate (includes "prod" alias)
if _is_production_env(ENV) and "localhost" in OAUTH_ISSUER_BASE:
    raise RuntimeError(
        "CLARITY_CLAUDE_OAUTH_ISSUER_BASE contains 'localhost' in production. "
        "Set to production URL (e.g., https://www.priority-guard.com)."
    )

# ============================================================================
# Fail-fast: every URL setting must be a real HTTPS production URL in prod/staging
# ============================================================================
#
# WHY THIS EXISTS. Ported from mcp_server/priority_guardian/config.py, which has
# carried this invariant since inc_05. MindSort-Claude had no equivalent: only
# OAUTH_ISSUER_BASE got a localhost check, so JWKS_URL, BACKEND_URL, MCP_SERVER_URL,
# MCP_RESOURCE_URL, CLARITY_ISSUER and CLARITY_AUDIENCE could each hold a localhost
# default in production and boot cleanly. Defaults in this module are localhost-based
# for dev convenience; silently accepting them in production serves a broken stack
# (JWKS unreachable, discovery publishes the wrong resource, persistence hits localhost).
#
# PREDICATE IS DELIBERATELY STRICTER THAN THE PG ORIGINAL. PG tests
# `"localhost" in value or value.startswith("http://")`, which does NOT reject the
# empty string ("localhost" in "" is False) nor a bare path like "/mcp". That hole is
# real: the audience boot guard below only checks CLARITY_CLAUDE_AUDIENCE ==
# CLARITY_CLAUDE_MCP_RESOURCE_URL, so setting BOTH to "" satisfies it and discovery
# then advertises "" as the resource. Requiring an https:// prefix subsumes empty,
# http://, and relative values in one rule; the localhost check stays because
# https://localhost:8003 would otherwise pass. PG-OpenAI still carries the weaker
# predicate — tracked separately, not changed here.
#
# DEPLOYMENT NOTE. Every value below is verified non-localhost in production as of
# 2026-08-01: MCP_RESOURCE_URL from the live discovery document, OAUTH_ISSUER_BASE
# from its authorization_servers entry, OAUTH_ISSUER_URL transitively via the
# same-origin invariant above, CLARITY_AUDIENCE via the byte-exact boot guard,
# CLARITY_ISSUER by its already-HTTPS default, and JWKS_URL / BACKEND_URL by the
# service functioning end-to-end (no token would validate and no board would persist
# under the localhost defaults).
if _is_production_env(ENV):
    _prod_url_invariants = {
        "CLARITY_CLAUDE_JWKS_URL": CLARITY_JWKS_URL,
        "CLARITY_CLAUDE_ISSUER": CLARITY_ISSUER,
        "CLARITY_CLAUDE_AUDIENCE": CLARITY_AUDIENCE,
        "CLARITY_CLAUDE_BACKEND_URL (BACKEND_URL)": BACKEND_URL,
        "CLARITY_CLAUDE_MCP_SERVER_URL (MCP_SERVER_URL)": MCP_SERVER_URL,
        "CLARITY_CLAUDE_MCP_RESOURCE_URL (MCP_RESOURCE_URL)": MCP_RESOURCE_URL,
        "CLARITY_CLAUDE_OAUTH_ISSUER_URL (OAUTH_ISSUER_URL)": OAUTH_ISSUER_URL,
        "CLARITY_CLAUDE_OAUTH_ISSUER_BASE (OAUTH_ISSUER_BASE)": OAUTH_ISSUER_BASE,
    }
    _invalid_urls = {
        name: value
        for name, value in _prod_url_invariants.items()
        if not value.startswith("https://") or "localhost" in value
    }
    if _invalid_urls:
        raise RuntimeError(
            f"Production URL validation failed. These env vars must be set to "
            f"HTTPS production URLs (not empty, not localhost, not http://, "
            f"not a bare path): {_invalid_urls}"
        )


# Supported OAuth scopes for MindSort Claude MCP server
# NOTE: This must mirror the clarity.* scopes in backend discovery
# (backend/core/oauth_provider/discovery.py → SCOPES_SUPPORTED).
# Unit tests in test_clarity_scope.py verify this invariant.
SCOPES_SUPPORTED = ["clarity.write"]


# ============================================================================
# Scope Definitions
# ============================================================================

TOOL_SCOPES = {
    "organize_thoughts": ["clarity.write"],
    "load_saved_board": ["clarity.write"],
    "read_board_before_editing": ["clarity.write"],
    "save_board": ["clarity.write"],
    "start_prioritization_flow": ["clarity.write"],
    "edit_board": ["clarity.write"],
    "delete_my_data": ["clarity.write"],
}


# ============================================================================
# Logging Configuration
# ============================================================================

# NOTE: Currently unused - logging is configured via structlog defaults.
# Reserved for future use if explicit log level control is needed.
# To use: import LOG_LEVEL in server.py and pass to structlog.configure().
LOG_LEVEL = get_env("LOG_LEVEL", default="INFO")


# ============================================================================
# CORS Configuration
# ============================================================================

# Environment detection for CORS
# Uses the inverse of canonical _is_production_env() for consistency.
# Note: staging is deliberately treated as production (IS_DEV=False) — it gets the same
# strict origin validation as production to catch CORS issues before they hit prod.
IS_DEV = not _is_production_env(ENV)

# Default allowed origins for Claude
# NOTE: Claude proxies widget calls, so direct browser access may not be needed.
# This is kept for dev mode and potential future use.
# UNVERIFIED-FOR-CLAUDE: Whether Claude's browser client hits this server directly
# is unconfirmed. Keep CORS for now; may be removable once behavior is confirmed.
_DEFAULT_CORS_ORIGINS = [
    "https://claude.ai",
]

# CORS allowed origins from environment
# SECURITY: Required in production to prevent silent breakage
CORS_ALLOWED_ORIGINS_RAW = get_env("CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS")

if _is_production_env(ENV) and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS must be explicitly set in production/staging. "
        "Set to comma-separated list of allowed origins "
        "(e.g., 'https://claude.ai')."
    )

# Parse origins from env var or use defaults (dev only)
CORS_ALLOWED_ORIGINS: list[str] = (
    [origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
    if CORS_ALLOWED_ORIGINS_RAW
    else _DEFAULT_CORS_ORIGINS
)
