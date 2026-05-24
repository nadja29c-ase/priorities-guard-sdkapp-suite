Briefing — Align OAuth Architecture with AS/RS Separation (remove PG_MCP_SERVER_URL from backend AS)
Why
The backend AS (www.priority-guard.com) currently injects a resource-server-specific WWW-Authenticate header into 401 responses from /oauth/* endpoints. This is wrong on two axes:

Correctness: The header points to pg.priority-guard.com/.well-known/oauth-protected-resource regardless of which app's OAuth route was called. A MindSort client hitting /oauth/mindsort/token with an expired token receives a WWW-Authenticate pointing to PG's resource metadata. Wrong resource.
Architecture: The AS shouldn't know about RS URLs at all. Per OAuth 2.1 and the MCP server implementation standard, each MCP server (RS) handles its own resource_metadata via its BearerAuthMiddleware. The AS's job is token issuance — not advertising resource metadata.
Operational cost: The PG_MCP_SERVER_URL field and its HTTPS validator are imported by every service that imports backend.core.config — including Celery. Every new SDK app would add a new <APP>_MCP_SERVER_URL env var to the backend config, the Celery service, and any future worker. This is a linear coupling cost for zero real benefit, since ChatGPT/Claude track their own resource state and don't need the AS's resource_metadata hint.

This briefing removes the coupling. The resource_metadata header emission is already correctly implemented in each MCP server's BearerAuthMiddleware (verified in the B2-7 review). This just removes the backend's redundant, incorrect version.
Scope narrowing — important: this briefing removes the specific mechanism by which backend emitted resource-server-specific WWW-Authenticate: Bearer resource_metadata="..." headers. It does NOT forbid the backend from ever emitting WWW-Authenticate headers. Generic OAuth challenges (e.g. Bearer realm="...", Basic realm="..." on invalid_client per RFC 6749 §5.2 + RFC 6750) remain legitimate AS behavior and may be added in the future without violating the AS/RS boundary. The forbidden thing is specifically any header that embeds MCP resource metadata.
Scope
One file of backend config, one file of main.py, two ADR updates, one new unit test file, Render env var cleanup. No changes to MCP server code. No changes to identity/reconciliation code.
Implementation — Copy and Adjust, Never Rewrite
Copy source files verbatim, make only the listed adjustments, never rewrite or restructure anything not explicitly listed.

Step 1 — Grep first, edit second
Before editing, run these greps across the repo to catch any call sites I may have missed:
grep -rn "PG_MCP_SERVER_URL" --include="*.py" --include="*.md" .
grep -rn "WWW_AUTHENTICATE_VALUE" --include="*.py" .
grep -rn "RESOURCE_METADATA_URL" --include="*.py" .
grep -rn "_MCP_ORIGIN" --include="*.py" .
Expected matches (known going in):

backend/core/config.py — defines all four
backend/main.py — imports WWW_AUTHENTICATE_VALUE, uses once in oauth_exception_handler
doc/ADR_003_oauth_provider_route_scope_mapping.md — mentions PG_MCP_SERVER_URL in Files Affected table

If the grep finds any additional call sites not listed above, stop and report them before proceeding. Do not edit additional files on your own judgment — flag them and wait.
Also check for any endpoints serving /.well-known/oauth-protected-resource on the backend by searching:
grep -rn "oauth-protected-resource" --include="*.py" backend/
If the backend serves this endpoint (it shouldn't, per ADR MCP Server Implementation Standard — this belongs on the MCP server), stop and report. Handling that case requires a separate decision.

Step 2 — Edit backend/core/config.py
Remove the field declaration:
Find:
python    # MCP Server URL for Priority Guardian (used for OAuth protected resource metadata)
    # This env var is shared with the MCP server deployment
    PG_MCP_SERVER_URL: str = "http://localhost:8003"
Delete these three lines entirely.
Remove the validator block for PG_MCP_SERVER_URL:
Inside validate_production_urls, find:
python        # PG_MCP_SERVER_URL: must be HTTPS
        mcp_parsed = urlparse(self.PG_MCP_SERVER_URL)
        if mcp_parsed.scheme != "https":
            raise ValueError(
                f"PG_MCP_SERVER_URL must use HTTPS in production. "
                f"Got: {self.PG_MCP_SERVER_URL!r} (scheme: {mcp_parsed.scheme})"
            )
Delete these seven lines entirely. Leave the other two URL validators (OAUTH_ISSUER, BACKEND_PUBLIC_URL) in place unchanged.
Also update the validator's docstring. Find:
python    @model_validator(mode='after')
    def validate_production_urls(self) -> 'Settings':
        """Validate production URL requirements (Increment 52).

        In production only:
        - OAUTH_ISSUER must use HTTPS and have no path component (B2-2 invariant)
        - BACKEND_PUBLIC_URL must use HTTPS
        - PG_MCP_SERVER_URL must use HTTPS
        """
Replace with:
python    @model_validator(mode='after')
    def validate_production_urls(self) -> 'Settings':
        """Validate production URL requirements (Increment 52).

        In production only:
        - OAUTH_ISSUER must use HTTPS and have no path component (B2-2 invariant)
        - BACKEND_PUBLIC_URL must use HTTPS
        """
Remove the derived constants at module bottom:
Find:
python# Derived constants for OAuth WWW-Authenticate header (B2-7 compliance)
# Used by main.py oauth_exception_handler and token_endpoint.py
# Extract origin only (scheme + host) - /.well-known/* URLs must be at the root
_parsed_mcp_url = urlparse(settings.PG_MCP_SERVER_URL)
_MCP_ORIGIN = f"{_parsed_mcp_url.scheme}://{_parsed_mcp_url.netloc}"
RESOURCE_METADATA_URL = f"{_MCP_ORIGIN}/.well-known/oauth-protected-resource"
WWW_AUTHENTICATE_VALUE = f'Bearer resource_metadata="{RESOURCE_METADATA_URL}"'
Delete these seven lines entirely.
Check if urlparse is still needed:
After the edits, urlparse is still used in validate_production_urls (for OAUTH_ISSUER and BACKEND_PUBLIC_URL). Leave the import alone.

Step 3 — Edit backend/main.py
Remove the import:
Find:
pythonfrom backend.core.config import settings, WWW_AUTHENTICATE_VALUE
Replace with:
pythonfrom backend.core.config import settings
Simplify oauth_exception_handler:
Find:
python@app.exception_handler(OAuthError)
async def oauth_exception_handler(request: Request, exc: OAuthError):
    """
    Handle OAuth errors with RFC 6749-compliant responses.

    Returns JSON error responses per OAuth 2.1 specification.
    Adds WWW-Authenticate header for 401 responses on /oauth/* paths (B2-7 compliance).
    """
    # Extract correlation_id for logging
    correlation_id = getattr(request.state, 'correlation_id', 'system')
    request_logger = logger.bind(correlation_id=correlation_id)

    request_logger.warning(
        "oauth.error",
        error=exc.error,
        description=exc.description,
        status_code=exc.status_code
    )

    # Build headers dict - add WWW-Authenticate for 401 on OAuth endpoints (B2-7)
    headers = {}
    if exc.status_code == 401 and request.url.path.startswith("/oauth/"):
        headers["WWW-Authenticate"] = WWW_AUTHENTICATE_VALUE

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error,
            "error_description": exc.description
        },
        headers=headers
    )
Replace with:
python@app.exception_handler(OAuthError)
async def oauth_exception_handler(request: Request, exc: OAuthError):
    """
    Handle OAuth errors with RFC 6749-compliant responses.

    Returns JSON error responses per OAuth 2.1 specification.

    Note on WWW-Authenticate: the AS does NOT emit WWW-Authenticate headers
    containing resource_metadata pointers to specific MCP servers. Each MCP
    server (Resource Server) emits its own resource_metadata header via its
    BearerAuthMiddleware — the AS does not know about RS URLs by design.

    This does NOT forbid generic OAuth challenges. If a future feature needs
    to emit a standard OAuth challenge (e.g. Bearer or Basic challenge on
    `invalid_client` at /token per RFC 6749 §5.2), that remains legitimate
    AS behavior and can be added here. What is forbidden is any header of
    the form `Bearer resource_metadata="..."` referencing an MCP server.

    See: ADR MCP Server Implementation Standard -> "Authorization Server /
    Resource Server Separation" -> "Backend Config Boundary".
    """
    # Extract correlation_id for logging
    correlation_id = getattr(request.state, 'correlation_id', 'system')
    request_logger = logger.bind(correlation_id=correlation_id)

    request_logger.warning(
        "oauth.error",
        error=exc.error,
        description=exc.description,
        status_code=exc.status_code
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error,
            "error_description": exc.description
        }
    )
Removed: the headers dict construction, the WWW-Authenticate injection, and the headers=headers kwarg on JSONResponse. Docstring updated to state the narrow invariant (no resource_metadata headers) while explicitly preserving the AS's right to emit generic OAuth challenges.

Step 4 — Update doc/ADR_003_oauth_provider_route_scope_mapping.md
Find the "Files Affected" section:
markdown## Files Affected

| File | Role |
|------|------|
| `backend/core/oauth_provider/register_client.py` | Route-to-scope mapping (current implementation) |
| `backend/core/oauth_provider/discovery.py` | `SCOPES_SUPPORTED` — single source of truth for valid scopes |
| `backend/core/oauth_provider/services/token_service.py` | Resource parameter handling (RFC 9728 B2-5) |
| `backend/core/config.py` | `OAUTH_ALLOWED_REDIRECT_URIS`, `PG_MCP_SERVER_URL` env vars |
Replace the last row with:
markdown| `backend/core/config.py` | `OAUTH_ALLOWED_REDIRECT_URIS` env var |
PG_MCP_SERVER_URL no longer belongs in backend config. Resource server URLs are owned by the MCP servers themselves.

Step 5 — Update doc/ADR_MCP Server Implementation Standard.md
Find the section "Authorization Server / Resource Server Separation" and add a new subsection at the end of it, after the "Verification Checklist — After Any Discovery Change" block but before the "Multi-App OAuth: One Shared AS, Multiple MCP Servers" section.
Add this subsection:
markdown#### Backend Config Boundary — What the AS May NOT Contain

The backend is an Authorization Server only. The following are **explicitly forbidden** in `backend/core/config.py`:

- Any MCP server URL (e.g. `PG_MCP_SERVER_URL`, `CLARITY_MCP_SERVER_URL`, any future `<APP>_MCP_SERVER_URL`)
- Any resource metadata URL derived from an MCP server URL
- Any WWW-Authenticate header template referencing resource_metadata

**Why:**

1. **Correctness.** The backend serves multiple app routes (`/oauth/pg/*`, `/oauth/mindsort/*`). A single resource_metadata header built from one MCP URL is wrong for all the others. A route-prefix-dispatched header would work but adds coupling that clients don't need (see point 3).

2. **Operational cost.** Every new SDK app would require a new `<APP>_MCP_SERVER_URL` env var on the backend service, the Celery service, and any future worker service that imports `backend.core.config`. This coupling is paid on every deploy and has caused production incidents (Celery crash, 2026-04-24) with zero offsetting benefit.

3. **Clients don't need it.** ChatGPT (Apps SDK) and Claude (MCP) both track the resource URL from the `resource=` parameter sent during `/authorize`. On 401 at the AS, they don't consult resource_metadata to find the resource — they already know it. The AS's header would be informational at best and misleading at worst.

**What the AS must NOT emit:**

Any WWW-Authenticate header of the form `Bearer resource_metadata="<url>"` referencing a specific MCP server's resource metadata. This was the removed behavior — the backend cannot emit a resource-specific header because it serves multiple app routes (`/oauth/pg/*`, `/oauth/mindsort/*`) and a single static header is correct for only one of them.

**What the AS may still emit:**

Generic OAuth challenges per RFC 6749 §5.2 remain legitimate AS behavior. For example, an `invalid_client` response at the token endpoint may include a `WWW-Authenticate: Basic realm="..."` or `Bearer realm="..."` challenge per RFC 6750, depending on the client authentication method. These are AS-scoped challenges (authenticating to the AS itself), not RS-scoped (pointing to a resource server).

The distinction: challenges that authenticate to the AS are fine. Challenges that advertise MCP resource metadata are forbidden.

Currently the backend emits no WWW-Authenticate headers at all. Future features that legitimately need generic OAuth challenges may add them to the appropriate handler (e.g. `oauth_exception_handler` for `invalid_client`) without violating this boundary.

**Where resource URLs belong:**

- Each MCP server's own `config.py` (`MCP_SERVER_URL`, `MCP_RESOURCE_URL`)
- Each MCP server's own `mcp_auth.py` (audience validation, resource_metadata builders)
- Each MCP server's own `server.py::BearerAuthMiddleware` (401/403 response construction)

**Historical context (for future maintainers):**

An earlier implementation (pre-April 2026) had the backend import a single `PG_MCP_SERVER_URL` env var and derive a `WWW_AUTHENTICATE_VALUE` used in the OAuth exception handler. This was removed when MindSort AI was added, because the header pointed at PG's resource metadata regardless of which app's route was called — a real correctness bug that masqueraded as working only because ChatGPT ignores the resource_metadata field on AS-origin 401s during refresh.

Step 6 — Create new unit test file
File: tests/unit/core/test_config_as_rs_boundary.py (new)
python"""
Architectural invariant tests for backend Settings.

Per ADR MCP Server Implementation Standard -> "Backend Config Boundary",
the backend is an Authorization Server only. Resource server URLs must
not appear in backend config.

These tests fail loudly if any <APP>_MCP_SERVER_URL or related field is
re-introduced into Settings.

Scope: these tests check module-level config declarations ONLY. They do
NOT attempt to constrain what headers handlers emit at runtime — generic
OAuth challenges (e.g. `Bearer realm="..."` on `invalid_client` at /token
per RFC 6749 §5.2) remain legitimate AS behavior.
"""

from backend.core.config import Settings


def test_settings_has_no_mcp_server_url_fields():
    """Settings must not declare any MCP_SERVER_URL-style field.

    Adding such a field means the backend is starting to know about RS
    URLs — an architectural violation. If you genuinely need per-app
    resource metadata, add it to the MCP server's own config, not here.
    """
    field_names = set(Settings.model_fields.keys())

    # Forbidden substrings — any field matching these is an AS/RS boundary violation
    forbidden_substrings = ("MCP_SERVER_URL", "MCP_RESOURCE_URL", "RESOURCE_METADATA")

    violations = [
        name for name in field_names
        if any(substr in name for substr in forbidden_substrings)
    ]

    assert not violations, (
        f"Backend Settings declared forbidden MCP/RS URL fields: {violations}. "
        f"Per ADR MCP Server Implementation Standard, the backend is an AS only. "
        f"Resource server URLs belong in the MCP server's own config.py."
    )


def test_backend_does_not_export_www_authenticate_value():
    """The backend must not export a module-level WWW-Authenticate constant
    derived from an MCP server URL.

    This test does NOT forbid the backend from emitting WWW-Authenticate
    headers in general — legitimate OAuth challenges per RFC 6749 §5.2
    remain allowed. What's forbidden is a shared, resource-specific template
    at the AS config level, because:

    1. It implies the AS knows about a specific RS's URL (wrong for multi-app)
    2. It was the mechanism by which resource_metadata leaked into backend
       OAuth error responses, pointing MindSort clients at PG's metadata

    Per-handler generic challenges (e.g. `Bearer realm="..."`) are fine and
    can be added inline in handler code without re-introducing a module-level
    resource-specific constant.
    """
    import backend.core.config as config_module

    forbidden_names = ("WWW_AUTHENTICATE_VALUE", "RESOURCE_METADATA_URL", "_MCP_ORIGIN")

    present = [name for name in forbidden_names if hasattr(config_module, name)]

    assert not present, (
        f"backend.core.config exports forbidden AS/RS boundary constants: {present}. "
        f"These were removed in the AS/RS separation cleanup. "
        f"If re-introduced, they will cause MindSort (and any future app's) OAuth "
        f"error responses to point to the wrong resource."
    )
Place under tests/unit/core/ alongside test_assert_no_duplicate_routes.py. Both tests are pure static checks — no DB, no Redis, no fixtures needed.

Step 7 — Integration test audit (not new test creation)
Grep for WWW-Authenticate in tests/integration/ to check existing test assertions:
grep -rn "WWW-Authenticate" tests/integration/
For each match, determine what the test asserts and apply the right action:

Asserts the header contains resource_metadata="..." → update the assertion to check "resource_metadata" not in response.headers.get("WWW-Authenticate", ""). The resource_metadata mechanism is what's being removed; the test needs to verify its absence, not the absence of the whole header.
Asserts the header contains a generic challenge (Bearer realm="...", Basic realm="...") → leave it alone. These remain legitimate AS behavior and unaffected by this change.
Asserts the header is entirely absent → leave it alone. Currently the backend emits no header; the test stays valid until/unless generic challenges are added later.

Do NOT write any new integration test asserting "no WWW-Authenticate header whatsoever on backend 401s." That would over-constrain future OAuth compliance work. The correct invariant is about resource_metadata content, not header presence.
If no matches are found: no integration test updates needed. Skip this step.

Step 8 — Render env var cleanup (manual step for Nadja, documented here for reference)
After the code ships and deploys cleanly:

Backend service on Render: remove PG_MCP_SERVER_URL env var. Keep OAUTH_ISSUER, BACKEND_PUBLIC_URL, INTERNAL_API_SECRET, all others unchanged.
Celery service on Render: remove PG_MCP_SERVER_URL env var (if set). The Celery crash resolves because nothing imports the field anymore.
PG MCP service on Render: keep PG_MCP_SERVER_URL, PG_MCP_RESOURCE_URL, PG_AUDIENCE, PG_ISSUER, PG_JWKS_URL, all its own URL vars. These belong on the RS, not the AS.
MindSort MCP service on Render: keep all CLARITY_* URL vars. Same reason.

This is a Render dashboard action, not a code change. Do it after the deploy succeeds and both PG and MindSort MCP services report healthy.

Acceptance criteria

 PG_MCP_SERVER_URL field removed from Settings class in backend/core/config.py
 Validator block for PG_MCP_SERVER_URL removed from validate_production_urls
 Validator docstring updated to remove PG_MCP_SERVER_URL mention
 _parsed_mcp_url, _MCP_ORIGIN, RESOURCE_METADATA_URL, WWW_AUTHENTICATE_VALUE all removed from backend/core/config.py
 backend/main.py no longer imports WWW_AUTHENTICATE_VALUE
 oauth_exception_handler no longer builds a headers dict, no longer passes headers= to JSONResponse, has updated docstring that preserves the right to emit generic OAuth challenges while forbidding resource_metadata headers
 ADR_003_oauth_provider_route_scope_mapping.md "Files Affected" row for backend/core/config.py no longer mentions PG_MCP_SERVER_URL
 ADR_MCP Server Implementation Standard.md has new subsection "Backend Config Boundary — What the AS May NOT Contain" with the narrow invariant stated ("resource_metadata headers forbidden, generic OAuth challenges allowed")
 New file tests/unit/core/test_config_as_rs_boundary.py exists with two tests, both passing
 Any existing integration test asserting WWW-Authenticate on backend 401 responses has been reviewed and updated per Step 7 rules (resource_metadata absence, not header absence)
 grep "PG_MCP_SERVER_URL" backend/ returns zero hits
 grep "WWW_AUTHENTICATE_VALUE" backend/ returns zero hits
 grep "RESOURCE_METADATA_URL" backend/ returns zero hits


Pre-deploy checklist (reminder)
Read doc/OPERATIONS_PREDEPLOY.md before committing. The key invariants it enforces (config schema, migration consistency, test pass) are all still relevant. Nothing about this change touches DB migrations, but the operations doc may have other pre-deploy tasks.
Run full unit + integration suite before pushing:
pytest tests/unit tests/integration -v
Expected result: all green, two new config-boundary tests pass, any previously-existing integration test asserting resource_metadata on backend 401 has been updated to check absence.

Post-deploy verification
After Render redeploys:

Backend health: hit / on www.priority-guard.com — should return landing page (proves import succeeded).
Celery: check Render Celery service logs — worker should boot without PG_MCP_SERVER_URL error.
PG MCP: trigger an expired-token scenario. Verify pg.priority-guard.com/mcp returns 401 with WWW-Authenticate containing resource_metadata="https://pg.priority-guard.com/.well-known/oauth-protected-resource". (This was already correct before; verify it still is.)
MindSort MCP: same test — mindsort.priority-guard.com/mcp should return 401 with WWW-Authenticate containing resource_metadata="https://mindsort.priority-guard.com/.well-known/oauth-protected-resource". (This was broken via backend header before; now each MCP handles its own — verify.)
Backend /oauth/pg/token with expired refresh token: verify response does NOT contain WWW-Authenticate: Bearer resource_metadata="...". A completely absent header is fine; a generic Bearer realm="..." or equivalent is also fine. What must NOT appear: any resource_metadata="..." pointer.
Fresh ChatGPT connection: run a full OAuth flow for PG MCP. Confirm ChatGPT completes auth, receives token, calls /mcp successfully. No regression.
Fresh ChatGPT connection for MindSort: same flow. Confirm no regression.


Files touched

backend/core/config.py — field + validator + derived constants removed
backend/main.py — import + resource_metadata header emission removed; docstring updated with narrowed invariant
doc/ADR_003_oauth_provider_route_scope_mapping.md — Files Affected row updated
doc/ADR_MCP Server Implementation Standard.md — new "Backend Config Boundary" subsection added with narrow invariant
tests/unit/core/test_config_as_rs_boundary.py — new file, two tests

Effort: ~30 min Claude Code + ~15 min review + Render env var cleanup (~5 min Nadja).

One concern worth flagging before shipping
The backend's oauth_provider_router may serve /.well-known/oauth-protected-resource at the backend's own origin (www.priority-guard.com). This would be architectural drift — per ADR, only MCP servers serve this endpoint at their own origins.
Claude Code: grep for oauth-protected-resource and well-known in the backend/core/oauth_provider/ directory and backend/core/routers/oauth_provider_router.py BEFORE editing. If any backend endpoint serves this, stop and report. Removing it is a separate decision because it might break a currently-working discovery flow. Don't touch it without Nadja's explicit go.

Rollback plan
If this ships and something breaks in ChatGPT's or Claude's OAuth flow:

Revert backend/main.py (restore the import + resource_metadata header emission)
Revert backend/core/config.py (restore the field + validator + derived constants)
Redeploy backend and Celery with PG_MCP_SERVER_URL=https://pg.priority-guard.com set on both services
Investigate root cause — likely candidate: a specific client implementation actually DID rely on the AS's resource_metadata header. Document this as evidence for framing 2 if true.

ADR changes can be left as-is during rollback (they're accurate about the intent, even if the implementation rolled back). Re-address after understanding the failure.

What this briefing is NOT doing

Not touching reconciliation code. Cross-device and cross-app identity are independent of this change.
Not touching MCP server code. PG MCP and MindSort MCP already emit their own resource_metadata correctly.
Not touching per-app reconcile endpoints. PG's exists, MindSort's doesn't yet — that's a separate increment.
Not touching ROUTE_SCOPE_REGISTRY in register_client.py. The AS knowing about scope-to-route mapping is fine; it's the AS's job to issue scoped tokens. That's different from knowing resource URLs.
Not forbidding all WWW-Authenticate emission from the backend. The invariant being established is specifically about resource_metadata headers pointing at MCP servers. Generic OAuth challenges (RFC 6749 §5.2) remain legitimate AS behavior and may be added in future features.
Not addressing the hypothetical future decision to move protected-resource metadata serving entirely to MCP servers. That's separate.

Ship this. Then decide if/when to fix the potential backend-serving-/.well-known/oauth-protected-resource drift, if Claude Code finds it.