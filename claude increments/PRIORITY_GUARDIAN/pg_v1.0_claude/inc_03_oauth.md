# Increment Claude-03: Deploy Claude Server + OAuth Allowlist Unblock

**Goal:** Deploy the Claude MCP server as a separate Render service and add Claude OAuth callback URIs to the backend allowlist. After this increment, end-to-end testing from Claude.ai is possible.

---

## Context

Two things are needed before end-to-end testing works:

1. The Claude MCP server needs to be running on a real HTTPS URL
2. The backend OAuth allowlist needs the four Claude callback URIs

Both changes are safe to do together:
- The Render service is a new, isolated service — zero risk to ChatGPT
- The allowlist change is purely additive — no existing ChatGPT URIs are touched

Reference: `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md`.

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No database migrations in this increment.

---

## Part A: Backend — Add Claude OAuth Callback URIs

### File: `backend/core/config.py`

**One change only.** Append four Claude URIs to the existing `_CHATGPT_REDIRECT_URIS` list. Do not rename the variable. Do not change the issuer, audience, scopes, or any other field. Do not touch any validators.

**Before:**
```python
_CHATGPT_REDIRECT_URIS: ClassVar[list[str]] = [
    "https://chatgpt.com/connector/oauth/",  # prefix — any connector callback_id
    "https://chatgpt.com/connector_platform_oauth_redirect",  # legacy
    "https://platform.openai.com/apps-manage/oauth",  # review
]
```

**After:**
```python
_CHATGPT_REDIRECT_URIS: ClassVar[list[str]] = [
    # ChatGPT (existing — do not modify)
    "https://chatgpt.com/connector/oauth/",  # prefix — any connector callback_id
    "https://chatgpt.com/connector_platform_oauth_redirect",  # legacy
    "https://platform.openai.com/apps-manage/oauth",  # review
    # Claude (new)
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "http://localhost:6274/oauth/callback",       # MCP Inspector + Claude Code
    "http://localhost:6274/oauth/callback/debug",  # MCP Inspector debug
]
```

**No other changes to `config.py`.**

### Unit tests

Add the two new tests to the existing file `tests/unit/core/test_normalize_redirect_uri.py`. Do not create a new test module.

1. `test_claude_callback_uri_accepted` — assert `https://claude.ai/api/mcp/auth_callback` passes `validate_redirect_uris` against the production allowlist (the `_CHATGPT_REDIRECT_URIS` list from `Settings`)
2. `test_chatgpt_uris_still_accepted` — assert all three existing ChatGPT URIs still pass (regression guard)

---

## Part B: Render Service Setup (operational — no code)

Create a new **Web Service** in the Render dashboard.

### Start command

Use the same start command pattern as the existing `priority-guardian-mcp` service on Render, replacing only the module path:

```
uvicorn mcp_server.priority_guardian_claude.server_dupl:create_app --factory --host 0.0.0.0 --port $PORT
```

### Service settings

| Setting | Value |
|---|---|
| Name | `priority-guardian-claude-mcp` |
| Repository | same repo as backend |
| Branch | `main` |
| Root directory | (leave empty — repo root) |
| Plan | Hobby |
| Region | Frankfurt |

### Required env vars

All env var names must exactly match the keys defined in `mcp_server/priority_guardian_claude/config.py`. Do not invent or abbreviate names — a single character mismatch silently uses the dev default and breaks OAuth in production.

| Env var | Value |
|---|---|
| `ENV` | `production` |
| `PG_CLAUDE_MCP_SERVER_URL` | `https://pg-claude.priority-guard.com` |
| `PG_CLAUDE_MCP_RESOURCE_URL` | `https://pg-claude.priority-guard.com/mcp` |
| `PG_CLAUDE_OAUTH_ISSUER_URL` | same as `PG_OAUTH_ISSUER_URL` on existing PG MCP service |
| `PG_CLAUDE_OAUTH_ISSUER_BASE` | same as `PG_OAUTH_ISSUER_BASE` on existing PG MCP service |
| `PG_CLAUDE_BACKEND_URL` | same as `PG_BACKEND_URL` on existing PG MCP service |
| `PG_CLAUDE_INTERNAL_API_SECRET` | same as `INTERNAL_API_SECRET` on existing PG MCP service |
| `PG_CLAUDE_JWKS_URL` | same as `PG_JWKS_URL` on existing PG MCP service |
| `PG_CLAUDE_ISSUER` | same as `PG_ISSUER` on existing PG MCP service |
| `PG_CLAUDE_AUDIENCE` | same as `PG_AUDIENCE` on existing PG MCP service |
| `PG_CLAUDE_CORS_ALLOWED_ORIGINS` | `https://claude.ai,https://claude.com` |
| `PG_CLAUDE_TOKEN_EXPIRY_GRACE_SECONDS` | `30` |
| `PG_CLAUDE_JWKS_CACHE_TTL_SECONDS` | `86400` |
| `PG_CLAUDE_JWKS_MAX_STALE_SECONDS` | `604800` |
| `PG_CLAUDE_JWKS_FETCH_TIMEOUT_SECONDS` | `5` |

### Domain mapping

Map `pg-claude.priority-guard.com` to the new Render service via IONOS DNS (same process as `pg.priority-guard.com`).

---

## Part C: Reachability Verification

Run all checks after deploy. These must all pass before attempting OAuth. The server will refuse to start in production if any critical env vars are missing — check Render logs first if any request fails unexpectedly.

```bash
# 1. Health check
curl https://pg-claude.priority-guard.com/health
# Expected: {"status": "ok", "service": "priority-guardian-claude-mcp"}

# 2. OAuth protected resource
curl https://pg-claude.priority-guard.com/.well-known/oauth-protected-resource | python3 -m json.tool

# 3. OAuth authorization server
curl https://pg-claude.priority-guard.com/.well-known/oauth-authorization-server | python3 -m json.tool

# 4. HEAD /mcp — must return 200
curl -I https://pg-claude.priority-guard.com/mcp

# 5. POST /mcp without token — must return 401 with WWW-Authenticate
curl -X POST https://pg-claude.priority-guard.com/mcp \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Critical invariants — all three must match exactly

| What | Must equal |
|---|---|
| URL used in Claude.ai connector setup | `PG_CLAUDE_MCP_RESOURCE_URL` on Render |
| `PG_CLAUDE_MCP_RESOURCE_URL` on Render | `resource` field in `/.well-known/oauth-protected-resource` response |
| `issuer` field in `/.well-known/oauth-authorization-server` response | `PG_CLAUDE_OAUTH_ISSUER_BASE` on Render (= backend `OAUTH_ISSUER`) |

The third invariant is sourced from `discovery_dupl.py` — `oauth_authorization_server()` sets `issuer = OAUTH_ISSUER_BASE`, which maps to `PG_CLAUDE_OAUTH_ISSUER_BASE`. If that env var is wrong, Claude's token validation fails silently.

The connector URL must include the `/mcp` suffix — this is `PG_CLAUDE_MCP_RESOURCE_URL`, not the server origin root.

### Optional: verify tool list before opening Claude.ai

Use MCP Inspector (`npx @modelcontextprotocol/inspector`) pointed at `https://pg-claude.priority-guard.com/mcp` to verify `list_tools` returns 7 public tools before proceeding to the Claude.ai connector. This catches tool listing failures before OAuth complicates debugging.

---

## Part D: End-to-End Connector Test

After Parts A, B, C are complete:

1. Open Claude.ai → Settings → Connectors → Add custom connector
2. Name: `Priority Guardian`
3. URL: `https://pg-claude.priority-guard.com/mcp` (must equal `PG_CLAUDE_MCP_RESOURCE_URL`)
4. Connect — OAuth flow should redirect to consent screen at `www.priority-guard.com`
5. Authenticate with `review@priority-guard.com` test account
6. Verify connector shows as connected
7. Verify tool list is visible in the connector (Claude should show the 7 public tools)

Tool calls producing correct output are not required yet — the goal is OAuth completes, connector connects, and tool list is non-empty.

---

## What NOT to Touch

- Any file in `mcp_server/priority_guardian/` — ChatGPT server
- Any existing URIs in `_CHATGPT_REDIRECT_URIS` — append only
- Any other backend files
- No Alembic migrations

---

## Definition of Done

- [ ] Four Claude URIs appended to `_CHATGPT_REDIRECT_URIS` in `backend/core/config.py`
- [ ] Both new unit tests pass, all existing redirect URI tests still pass
- [ ] Backend redeployed on Render
- [ ] Claude Render service deployed — health check returns 200
- [ ] `/.well-known/oauth-protected-resource` `resource` field equals `https://pg-claude.priority-guard.com/mcp`
- [ ] `/.well-known/oauth-authorization-server` `issuer` field equals `PG_CLAUDE_OAUTH_ISSUER_BASE`
- [ ] HEAD `/mcp` returns 200
- [ ] POST `/mcp` without token returns 401 with `WWW-Authenticate` header
- [ ] OAuth flow completes end-to-end from Claude.ai custom connector with test account
- [ ] Tool list visible in Claude connector (non-empty — 7 public tools)