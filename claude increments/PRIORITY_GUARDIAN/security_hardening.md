# Security Hardening — Internal API Auth + CSP Header

**Type:** Cross-cutting security hardening  
**Scope:** PG backend routers, PG MCP http_client, shared middleware  
**Risk addressed:** IDOR via network misconfiguration (Medium severity)  
**No database migrations required.**

---

## Context

A security audit identified an inconsistency between Clarity and Priority Guardian:

- **Clarity** MCP server sends `X-Internal-Secret` header → Clarity backend router verifies it via `_verify_internal_call()` in `clusters_router.py`
- **Priority Guardian** MCP server does NOT send it → PG backend routers do NOT verify it

All PG routers rely solely on `X-User-ID` header (UUID validation only). `X-User-ID` is an identity selector, not authentication. If the backend is ever directly exposed (Render misconfiguration, routing change), anyone can set `X-User-ID` to any UUID and access any user's data.

Authentication for PG internal endpoints becomes: `X-Internal-Secret` (shared secret) + network boundary. This is the same model Clarity already uses.

Additionally, the `SecurityHeadersMiddleware` in `backend/core/middleware.py` lacks a `Content-Security-Policy` header. Since the backend serves HTML pages (OAuth consent, landing, privacy, terms), CSP provides defense-in-depth against XSS.

---

## Fix 1: Internal API Secret Enforcement on PG Routers

### What exists today (Clarity — the reference implementation)

**Clarity MCP config** (`mcp_server/clarity/config.py`):
```
INTERNAL_API_SECRET = get_env("INTERNAL_API_SECRET", default="")
```

**Clarity MCP persistence** (`mcp_server/clarity/persistence.py`):
Sends `X-Internal-Secret` header on every backend call when secret is non-empty.

**Clarity backend router** (`backend/apps/clarity/routers/clusters_router.py`):
Has `_verify_internal_call(request)` that checks `X-Internal-Secret` against `settings.INTERNAL_API_SECRET`. Skips verification when secret is empty (dev mode). Returns 403 "Forbidden" on mismatch. Applied per-endpoint (called manually in each handler).

**Backend config** (`backend/core/config.py`):
Already has `INTERNAL_API_SECRET` setting with production validator that prevents startup if empty in production.

### What needs to change

**A. PG MCP server — config**

File: `mcp_server/priority_guardian/config.py`

Add `INTERNAL_API_SECRET` config variable. Use the same env var name as Clarity (`INTERNAL_API_SECRET`) since it's the same shared secret for backend authentication. Default to empty string for dev mode. Same pattern as Clarity's config.

**B. PG MCP server — http_client**

File: `mcp_server/priority_guardian/http_client.py`

All four functions (`backend_get`, `backend_post`, `backend_put`, `backend_delete`) currently build headers with only `X-User-ID` and `X-Correlation-ID`. Each must also send `X-Internal-Secret` when the config value is non-empty. Import `INTERNAL_API_SECRET` from the PG MCP config.

**C. PG backend — shared dependency**

File: `backend/apps/priority_guardian/dependencies.py`

Add a `verify_internal_call` function as a FastAPI dependency. Use FastAPI's `Header()` injection (idiomatic, testable):

```
x_internal_secret: str | None = Header(default=None, alias="X-Internal-Secret")
```

Logic:
- If `settings.INTERNAL_API_SECRET` is empty → return (dev mode, skip)
- If header is missing or doesn't match → raise `HTTPException(403, detail="Forbidden")`
- Response body MUST be generic: just `"Forbidden"`. Never reveal expected vs actual secret.

**D. PG backend — apply at ROUTER LEVEL, not per-endpoint**

This is the key improvement over Clarity's per-endpoint pattern. Apply `verify_internal_call` as a router-level dependency so every future endpoint added to these routers is automatically protected.

Each PG router that handles user data must be instantiated with `dependencies=[Depends(verify_internal_call)]`. The routers to update:

| Router file | Current `APIRouter()` call |
|---|---|
| `priorities_router.py` | Add `dependencies=[Depends(verify_internal_call)]` to `APIRouter()` |
| `calendar_router.py` | Add `dependencies=[Depends(verify_internal_call)]` to `APIRouter()` |
| `snapshot_router.py` | Add `dependencies=[Depends(verify_internal_call)]` to `APIRouter()` |
| `weekly_report_router.py` | Add `dependencies=[Depends(verify_internal_call)]` to `APIRouter()` |
| `pattern_router.py` | Add `dependencies=[Depends(verify_internal_call)]` to `APIRouter()` |
| `offboarding_router.py` | Add `dependencies=[Depends(verify_internal_call)]` to `APIRouter()` |
| `google_connection_router.py` | Add `dependencies=[Depends(verify_internal_call)]` to `APIRouter()` |

**DO NOT** add it to:
- `health_router.py` — health checks have no user data, must remain unauthenticated for Render health monitoring

This makes it impossible to add a new PG endpoint without protection. Any new endpoint added to these routers automatically inherits the dependency.

**E. Env var deployment**

The `INTERNAL_API_SECRET` env var already exists in the backend's Render environment (required by `config.py` production validator). The PG MCP server on Render needs the same env var added. Use the SAME value as the backend — it's one shared secret.

---

## Fix 2: Content-Security-Policy Header

File: `backend/core/middleware.py`

In `SecurityHeadersMiddleware.dispatch()`, add CSP to the headers dict:

```
"Content-Security-Policy": "default-src 'self'; base-uri 'self'; object-src 'none'; script-src 'none'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
```

Rationale:
- `default-src 'self'` — only load resources from same origin
- `base-uri 'self'` — prevents `<base>` tag injection attacks
- `object-src 'none'` — blocks Flash/plugin-based XSS vectors
- `script-src 'none'` — the served HTML pages (consent, landing, privacy, terms) do not use JavaScript
- `style-src 'self' 'unsafe-inline'` — allow inline styles (consent pages use inline CSS)
- `frame-ancestors 'none'` — reinforces X-Frame-Options DENY

If after implementation any consent page breaks due to inline scripts, adjust `script-src` to `'self'`. Check the consent templates in `backend/templates/oauth_consent_*.html` to verify they don't use `<script>` tags.

---

## Acceptance Criteria

### Fix 1 — Internal API Secret

1. When `INTERNAL_API_SECRET` is set (production mode):
   - PG backend routers return 403 `{"detail": "Forbidden"}` when `X-Internal-Secret` is missing
   - PG backend routers return 403 `{"detail": "Forbidden"}` when `X-Internal-Secret` is wrong
   - PG backend routers accept requests when `X-Internal-Secret` matches
   - Response body never contains the actual or attempted secret value
   - Health endpoint remains accessible without any auth headers

2. When `INTERNAL_API_SECRET` is empty (dev mode):
   - All PG endpoints work without `X-Internal-Secret` header (backward-compatible)

3. PG MCP http_client sends `X-Internal-Secret` on every backend call when configured

4. Existing PG unit and integration tests pass (they run in dev mode with empty secret)

5. Router-level enforcement: any new endpoint added to a protected PG router is automatically protected

### Fix 2 — CSP Header

1. All HTTP responses include `Content-Security-Policy` header
2. OAuth consent pages render correctly with the new CSP
3. Landing page, privacy page, terms page render correctly

---

## Unit Tests

File: `tests/unit/priority_guardian/test_internal_auth.py` (new file)

Test the `verify_internal_call` dependency function in isolation:
- Missing header + non-empty secret → HTTPException 403 with detail "Forbidden"
- Wrong header + non-empty secret → HTTPException 403 with detail "Forbidden"
- Correct header + non-empty secret → no exception (returns None)
- Empty secret (dev mode) → no exception regardless of header presence
- 403 response body never contains the secret value

File: `tests/unit/priority_guardian/test_http_client.py` (extend existing)

Test that PG MCP http_client includes `X-Internal-Secret` in request headers when configured, and omits it when empty.

File: `tests/unit/core/test_middleware.py` (extend existing)

Test that `Content-Security-Policy` header is present in responses from `SecurityHeadersMiddleware` and contains the expected directives.

---

## Integration Tests

File: `tests/integration/priority_guardian/test_internal_auth.py` (new file)

Follow the pattern from `tests/integration/clarity/test_internal_auth.py` but adapted for PG endpoints.

**Important: 403 rejection tests do NOT need database fixtures.** The request is rejected at the dependency level before any DB access. Only tests that verify successful (200/201) responses need a test user.

### Production mode tests (patch `settings.INTERNAL_API_SECRET` to a test value):

403 paths — no DB fixtures needed, just call endpoint and assert rejection:
- `GET /api/priority-guardian/priorities` without `X-Internal-Secret` → 403
- `GET /api/priority-guardian/priorities` with wrong `X-Internal-Secret` → 403
- `POST /api/priority-guardian/priorities` without `X-Internal-Secret` → 403
- `GET /api/priority-guardian/calendar/time-allocation` without `X-Internal-Secret` → 403
- `POST /api/priority-guardian/disconnect` without `X-Internal-Secret` → 403
- 403 response body is exactly `{"detail": "Forbidden"}` — no secret leakage

Health exempt — no DB fixtures needed:
- `GET /api/priority-guardian/health` without `X-Internal-Secret` → 200

200 path — needs a test user in database:
- `GET /api/priority-guardian/priorities` with correct `X-Internal-Secret` + valid `X-User-ID` → 200

### Dev mode tests (patch `settings.INTERNAL_API_SECRET` to empty string):

- `GET /api/priority-guardian/priorities` without `X-Internal-Secret` → passes through to normal handling (needs test user for 200)

---

## Pre-Deploy Checklist

- [ ] Verify `INTERNAL_API_SECRET` env var is set on PG MCP server in Render (same value as backend)
- [ ] Verify consent templates in `backend/templates/oauth_consent_*.html` don't use `<script>` tags (CSP compatibility)
- [ ] Run full test suite
- [ ] After deploy: manually verify `GET /api/priority-guardian/health` returns 200 without any auth headers
- [ ] After deploy: verify PG MCP tools still work end-to-end in ChatGPT (the MCP server now sends the secret, backend now requires it)
