# Priority Guardian — Increment 01: Foundation (Pipes)

**Goal:** Priority Guardian (PG) becomes a fully wired SDK app in the Priority Guard Suite. After this increment: PG has its own backend module, its own MCP server, OAuth flow works end-to-end, and Google Calendar connect/disconnect tools work through ChatGPT.

**No business logic. No data models. No widget. Just pipes.**

---

## Status Quo — What Already Exists

### Shared Infrastructure (DO NOT recreate)
- PostgreSQL: `core_users`, `core_connections`, `core_consents`, `oauth_access_tokens`, `oauth_authorization_codes` — all shared across SDK apps
- Redis: caching, rate limiting, OAuth state, job queues
- Celery: background jobs
- Google OAuth client flow: `core/google_oauth.py`, `core/routers/oauth_google_router.py`
- OAuth 2.1 provider: full implementation in `core/oauth_provider/`
- Encryption, logging, middleware, rate limiting — all in `core/`

### OAuth Provider — PG Routes Already Dual-Decorated
All OAuth provider endpoints already serve both `/oauth/focused/` AND `/oauth/pg/` paths:
- `authorize.py` → `@router.get("/oauth/pg/authorize")` ✅
- `consent_ui.py` → `@router.post("/oauth/pg/consent")` ✅
- `jwks.py` → `@router.get("/oauth/pg/jwks")` ✅
- `token_endpoint.py` → `@router.post("/oauth/pg/token")` ✅
- `register_client.py` → `@router.post("/oauth/pg/register")` ✅
- `revoke.py` → `@router.post("/oauth/pg/revoke")` ✅

The `/oauth/pg/` path prefix represents the **Priority Guard suite**, not the Priority Guardian app specifically.

### Backend Discovery — Already Points to `/oauth/pg/` Paths
`backend/core/oauth_provider/discovery.py` already returns `/oauth/pg/authorize`, `/oauth/pg/token`, etc.

### Existing SDK Apps for Reference
- `backend/apps/focused/` — full app with routers, tools, logic, models, utils
- `backend/apps/clarity/` — simpler app with routers, models, db_models
- `mcp_server/focused/` — full MCP server with config, discovery, auth, server
- `mcp_server/clarity/` — full MCP server with handlers, tools, widget
- `mcp_server/sharpen/` — stateless MCP server (no OAuth)
- `mcp_server/shared/google_tools.py` — reusable connect/disconnect logic (DO NOT modify in this increment)

### Port Allocation
- Backend: 8000
- Focused MCP: 8001
- Clarity MCP: 8002
- **Priority Guardian MCP: 8003**

---

## What Needs to Be Created

### 1. Backend App Module

**Location:** `backend/apps/priority_guardian/`

**Follow the folder structure pattern of `backend/apps/focused/`** but stripped to foundation-only:
- App config with PG_APP_NAME and PG_APP_DISPLAY_NAME constants
- Health router: service name `"priority-guardian-backend"`, tag `"priority-guardian-health"`, endpoint `GET /health`
- Google connection router: structurally identical to Focused's — queries same `core_connections` table WHERE provider='google'. Two endpoints: connection-status (GET) and initiate-connection (POST)
- Offboarding router: minimal, disconnect endpoint only (`POST /disconnect`). Follows Focused's `offboarding_router.py` pattern but simpler — PG has no webhooks, no app-specific sessions, no PG-specific Redis cache. Just revoke Google connection from `core_connections` and mark PG OAuth tokens as revoked. Must be idempotent.
- Models package: empty placeholder for future request/response models

The disconnect endpoint lives under PG's own prefix (`/api/priority-guardian/disconnect`), NOT Focused's. No cross-app prefix routing — each app owns its full API surface.

No business logic modules. No tools. No db_models. No sync logic. No webhook handling.

### 2. Register PG in main.py

Mount PG routers in `backend/main.py`:
- Health router at prefix `/api/priority-guardian`
- Google connection router at prefix `/api/priority-guardian/google`
- Offboarding router at prefix `/api/priority-guardian` (provides `POST /disconnect`)

Follow import grouping style of existing routers in main.py.

### 3. OAuth Provider Updates — Single PG Scope

#### 3A. Discovery — Register Scope
In `backend/core/oauth_provider/discovery.py`, add to `SCOPES_SUPPORTED`:
- `pg.access`

This is a single temporary scope to prove the OAuth pipe works. Scope taxonomy (`pg.read` / `pg.write`) will be introduced in Increment 02 when tools with different permission levels exist.

Keep sorted alphabetically (existing convention).

#### 3B. Authorize — Scope Description + Consent Template Routing

**Scope description (EN and DE):**
- `pg.access` — EN: "Allow Priority Guardian to connect your Google Calendar and read events to track time on your priorities." / DE: "Priority Guardian erlauben, deinen Google Kalender zu verbinden und Termine zu lesen, um die Zeit für deine Prioritäten zu erfassen."

**Consent template routing:** In the template selection logic in `authorize.py`, add a PG condition: if any requested scope starts with `"pg."`, use PG consent template and filter displayed scopes to only `pg.*`. Place this condition AFTER the Clarity check, BEFORE the Focused else-branch. Override display name to "Priority Guardian".

Template names: `oauth_consent_pg_en.html`, `oauth_consent_pg_de.html`

#### 3C. Register Client — Default Scopes

In `register_client.py`, change `DEFAULT_SCOPES_PG` to `["pg.access"]` only. Remove `clarity.write` from PG suite defaults — bundling scopes across apps creates audit noise and unnecessary coupling. Each MCP server's discovery advertises only its own scopes; Clarity's MCP server requests `clarity.write` explicitly during authorization, so it doesn't depend on suite-level defaults.

### 4. Consent Templates

Create two consent templates in `backend/templates/`:
- `oauth_consent_pg_en.html`
- `oauth_consent_pg_de.html`

**Quick clone of `oauth_consent_clarity_en.html` / `oauth_consent_clarity_de.html`.** Only change:
- App name: "Priority Guardian"
- Scope descriptions: use PG-specific description from 3B

Everything else stays identical: layout, buttons, privacy link, hidden fields, form action. No copy polish, no final wording, no UX refinement — those belong in a later increment when PG's value proposition is stable.

### 5. MCP Server

**Location:** `mcp_server/priority_guardian/`

**Follow the folder structure pattern of `mcp_server/focused/`.**

#### 5A. Config
Environment variables prefixed with `PG_`:
- `PG_JWKS_URL` (default: `http://localhost:8000/oauth/pg/jwks`)
- `PG_ISSUER` (default: `https://www.priority-guard.com`)
- `PG_AUDIENCE` (default: `https://www.priority-guard.com`)
- `CHATGPT_CLIENT_ID_PG` (required in prod/staging)
- `PG_BACKEND_URL` (default: `http://localhost:8000`)
- `PG_MCP_SERVER_URL` (default: `http://localhost:8003`)
- `PG_OAUTH_ISSUER_URL` (default: `http://localhost:8000/oauth/pg`)

Scopes supported: `["pg.access"]`

Tool-to-scope mapping:
- `connect_google_calendar` → `["pg.access"]`
- `disconnect_google_calendar` → `["pg.access"]`

Tool annotations (required for OpenAI store review):
- `connect_google_calendar`: `openWorldHint: true`, `readOnlyHint: false` (triggers external OAuth flow with side effects)
- `disconnect_google_calendar`: `openWorldHint: true`, `readOnlyHint: false`, `destructiveHint: true` (revokes access, deletes connection)

Default port: 8003

#### 5B. Discovery
Three discovery endpoints returning PG-specific URLs. Same pattern as `mcp_server/focused/discovery.py` but using PG config values.

#### 5C. MCP Auth
Copy of `mcp_server/focused/mcp_auth.py` with imports changed to PG config. Same JWKS caching, JWT validation, scope enforcement, RFC 6750 error builders. This is not new engineering — it's instantiation of existing infrastructure for a new app.

#### 5D. Server
FastMCP instance named `"priority-guardian-mcp"`, streamable_http_path="/mcp".

**Google Calendar tools — thin wrapper approach:**
DO NOT modify `mcp_server/shared/google_tools.py`. That file hardcodes Focused backend paths (`/api/focused/google/...`) and Focused is in production. Instead, implement `connect_google_calendar` and `disconnect_google_calendar` directly in PG's server.py as thin wrappers that call `backend_get`/`backend_post` with PG-specific paths:
- `/api/priority-guardian/google/connection-status`
- `/api/priority-guardian/google/initiate-connection`
- `/api/priority-guardian/disconnect` (offboarding router)

Follow the same logic flow as `shared/google_tools.py` (check status → return connected or generate URL / require confirmation → call disconnect), just with PG paths and PG auth. Both tools must be idempotent (retry-safe). Refactor to shared when a third app needs it.

No CORS middleware (no widget). No other tools.

ASGI entrypoint: `app = create_app()` at module level.

### 6. Environment Variables

Add to `.env.example`:
```
# Priority Guardian MCP Server
PG_BACKEND_URL=http://localhost:8000
PG_MCP_SERVER_URL=http://localhost:8003
PG_OAUTH_ISSUER_URL=http://localhost:8000/oauth/pg
PG_JWKS_URL=http://localhost:8000/oauth/pg/jwks
PG_ISSUER=https://www.priority-guard.com
PG_AUDIENCE=https://www.priority-guard.com
CHATGPT_CLIENT_ID_PG=
```

---

## Testing

### Unit Tests

**Location:** `tests/unit/mcp_priority_guardian/`

Minimal smoke tests for the auth module. No network, all mocked.

| Test Case | Verify |
|---|---|
| Missing Authorization header | Returns UnauthorizedError |
| Malformed Bearer token | Returns UnauthorizedError |
| Valid token, correct scope | Auth passes, returns user context |

Follow pattern in `tests/unit/mcp_focused/test_mcp_auth_helpers.py`. Mock JWT validation.

### Integration Tests

**Location:** `tests/integration/priority_guardian/`

| Test Case | Verify |
|---|---|
| GET /api/priority-guardian/health → 200 | Response contains `"service": "priority-guardian-backend"` |
| GET /api/priority-guardian/google/connection-status (with X-User-ID) | Returns `{"connected": false}` for unknown user |
| PG scope in /.well-known/openid-configuration | `pg.access` present in `scopes_supported` |

Do NOT break any existing tests.

---

## What This Increment Does NOT Include

- No database models / Alembic migrations (Increment 02)
- No business logic tools
- No widget or React code
- No Celery jobs or background tasks
- No onboarding router
- No `DELETE /delete-data` endpoint (GDPR Art. 17 — deferred to later increment)
- No scope taxonomy (`pg.read` / `pg.write`) — deferred to Increment 02 when tools exist
- No modification to `mcp_server/shared/google_tools.py`
- No consent template copy polish or localization refinement

---

## Production Readiness (Increment Context)

This is a foundation increment. Production readiness at this level means:
- OAuth flow works end-to-end (authorize → consent → token → MCP auth)
- MCP server auth is fail-closed (reject on any validation error)
- Health endpoint available for uptime monitoring
- No new dependencies added
- All endpoints async, no blocking calls
- Structured logging via structlog, never log tokens or PII

---

## Success Criteria

- `backend/apps/priority_guardian/` exists with health + google connection routers
- `mcp_server/priority_guardian/` exists with server, config, discovery, auth
- `GET /api/priority-guardian/health` returns 200 OK
- `pg.access` appears in `/.well-known/openid-configuration` scopes_supported
- Consent template renders for PG scope requests
- `connect_google_calendar` tool works via PG MCP server
- `disconnect_google_calendar` tool works via PG MCP server
- All tests pass (new + existing)
- PG MCP server starts without errors on port 8003

---

## Files Modified (Existing)

| File | Change |
|---|---|
| `backend/main.py` | Import + mount PG routers |
| `backend/core/oauth_provider/discovery.py` | Add pg.access to SCOPES_SUPPORTED |
| `backend/core/oauth_provider/authorize.py` | Add PG scope description (EN+DE), add PG template routing |
| `backend/core/oauth_provider/register_client.py` | Change DEFAULT_SCOPES_PG to `["pg.access"]` only |
| `.env.example` | Add PG MCP env vars |

## Files Created (New)

| File | Purpose |
|---|---|
| `backend/apps/priority_guardian/__init__.py` | App module |
| `backend/apps/priority_guardian/pg_config.py` | App constants |
| `backend/apps/priority_guardian/routers/__init__.py` | Router package |
| `backend/apps/priority_guardian/routers/health_router.py` | Health check |
| `backend/apps/priority_guardian/routers/google_connection_router.py` | Google connect endpoints (status + initiate) |
| `backend/apps/priority_guardian/routers/offboarding_router.py` | Disconnect endpoint only |
| `backend/apps/priority_guardian/models/__init__.py` | Models package |
| `backend/apps/priority_guardian/models/requests.py` | Placeholder |
| `backend/templates/oauth_consent_pg_en.html` | PG consent (English) — quick clone |
| `backend/templates/oauth_consent_pg_de.html` | PG consent (German) — quick clone |
| `mcp_server/priority_guardian/__init__.py` | MCP module |
| `mcp_server/priority_guardian/config.py` | MCP config |
| `mcp_server/priority_guardian/discovery.py` | OAuth discovery |
| `mcp_server/priority_guardian/mcp_auth.py` | JWT auth (copy from Focused) |
| `mcp_server/priority_guardian/server.py` | MCP server + Google tools thin wrappers |
| `tests/unit/mcp_priority_guardian/__init__.py` | Test package |
| `tests/unit/mcp_priority_guardian/test_pg_mcp_auth.py` | Auth smoke tests |
| `tests/integration/priority_guardian/__init__.py` | Test package |
| `tests/integration/priority_guardian/test_pg_health.py` | Health + scope smoke tests |
