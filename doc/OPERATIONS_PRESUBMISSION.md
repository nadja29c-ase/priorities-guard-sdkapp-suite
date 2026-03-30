# Pre-Submission Operations Checklist 03/26

**Purpose:** Prepare the app for successful OpenAI store review. This checklist covers configuration, compliance, and verification steps that prevent common rejection causes.

Run through this checklist before submitting any SDK app to the OpenAI store.

## Render Environment

- [ ] **ENV=production** on Render for ALL services (backend, MCP servers)
- [ ] Verify: `ENV` is not `dev`, `development`, or `local` on any production service
- [ ] All `required=True` config values have env vars set (will fail-fast at startup if missing)
- [ ] `INTERNAL_API_SECRET` set and matching between backend and MCP server(s)
- [ ] `CORS_ALLOWED_ORIGINS` explicitly set (required in production)
- [ ] **`CORS_ALLOWED_ORIGINS` contains NO localhost entries** — remove any `http://localhost:*` values added during testing. Production value must be exactly: `https://web-sandbox.oaiusercontent.com,https://chatgpt.com,https://chat.openai.com`
- [ ] **Upgrade Render from Free to Hobby tier** — free tier spins down after inactivity, causing cold starts that can exceed OpenAI's timeout on first tool call

## Domain / ui.domain Verification

**This is the #1 cause of "unable to connect" rejections. Confirmed cause of Clarity's first rejection.**

- [ ] `ui.domain` in `_meta` matches the actual MCP server origin that OpenAI will reach
- [ ] Verify dynamically: `ui.domain` must come from env var via `_extract_origin()`, NOT hardcoded
- [ ] Hit the MCP server URL in browser — confirm it resolves and returns health check
- [ ] No path component in `ui.domain` (pure origin only: `https://host.com`, not `https://host.com/mcp`)

### ⚠️ CRITICAL: Submission URL must match `MCP_SERVER_URL` env var on Render

The URL you enter in the OpenAI store submission form **must exactly match** what `PG_MCP_SERVER_URL` (or equivalent) is set to on Render. This controls what the `resource` field returns in `/.well-known/oauth-protected-resource`. If these differ, ChatGPT connects via one URL but the `resource` claim points to another — OAuth discovery breaks silently.

**Before every submission, verify this three-way match:**

| What | Must equal |
|---|---|
| URL entered in OpenAI submission form | `PG_MCP_SERVER_URL` env var on Render |
| `PG_MCP_SERVER_URL` env var on Render | `resource` field in `/.well-known/oauth-protected-resource` response |

If you submit with a custom domain (e.g. `https://pg.priority-guard.com`), `PG_MCP_SERVER_URL` on Render must be set to that custom domain — not the `onrender.com` URL.

```bash
# Step 1: Check what oauth-protected-resource returns
curl https://<SUBMISSION_URL>/.well-known/oauth-protected-resource
# → "resource" field must equal <SUBMISSION_URL>

# Step 2: Confirm Render env var matches
# Render Dashboard → service → Environment → PG_MCP_SERVER_URL
```

### Per-app verification commands

```bash
# PG MCP — should return {"status": "ok", ...}
curl https://pg.priority-guard.com/

# MindSort AI MCP — should return {"status": "ok", ...}
curl https://priorities-guard-clarity-mcp.onrender.com/
```

Cross-check: the origin from `curl` must match what the app returns in `_meta.ui.domain` at runtime.

### Known issues (confirmed rejection causes)

**Clarity rejection:** Hardcoded `"https://clarity.priority-guard.com"` as `ui.domain` while the MCP server ran at `https://priorities-guard-clarity-mcp.onrender.com`. Fix: use `_extract_origin(MCP_SERVER_URL)` pattern driven by env var.

**PG near-miss:** `oauth-protected-resource` was returning the `onrender.com` URL while the submission planned to use the custom domain `pg.priority-guard.com`. Would have broken OAuth discovery on first connection attempt.

## OAuth Issuer Consistency Check

**Do not change `OAUTH_ISSUER` on the backend or `PG_ISSUER`/`PG_AUDIENCE` on the MCP server unless you are doing a deliberate coordinated migration.**

`OAUTH_ISSUER` is used throughout the OAuth flow — it is the `iss` claim in every JWT, and the base URL for all discovery endpoints (`authorization_endpoint`, `token_endpoint`, `jwks_uri`, `registration_endpoint`). It is NOT just for browser-facing pages.

**The rule to uphold:** `OAUTH_ISSUER` on the backend and the MCP server's `PG_ISSUER`/`PG_AUDIENCE` must always use the **same `onrender.com` URL end-to-end**. The custom domain `www.priority-guard.com` is reserved exclusively for browser-facing endpoints (consent screen, privacy policy, homepage) and must never be used as `OAUTH_ISSUER`. Do not "upgrade" `OAUTH_ISSUER` to the custom domain — it would silently break JWT validation on every tool call.

**Before every submission, verify this is still true:**

```bash
# Backend issuer (from live discovery endpoint)
curl -s https://<BACKEND_URL>/.well-known/openid-configuration | jq .issuer

# MCP server expected issuer (PG_ISSUER env var on Render)
# Must match the value above exactly

# MCP server expected audience (PG_AUDIENCE env var on Render)
# Must also match OAUTH_ISSUER — backend sets aud = OAUTH_ISSUER on tokens
```

| Env var | Must equal |
|---|---|
| Backend `OAUTH_ISSUER` | `issuer` in `/.well-known/openid-configuration` response |
| MCP `PG_ISSUER` | Backend `OAUTH_ISSUER` |
| MCP `PG_AUDIENCE` | Backend `OAUTH_ISSUER` |

If any of these three differ, JWT validation will fail with `invalid_token` on every tool call.

## OAuth / redirect_domains

- [ ] `redirect_domains` in `openai/widgetCSP` matches the backend origin used for OAuth `/authorize`
- [ ] OAuth flow works end-to-end in ChatGPT (not just MCP Inspector)
- [ ] Demo account ready: pre-populated Google Calendar data, no MFA, no extra sign-up steps

## Widget Build

- [X] Widget built and HTML copied to `widgets/` directory
- [X] Built HTML is the production build (not dev mode)
- [X] No `style=` attributes containing hardcoded hex colors (run grep check below)

```bash
# Should return NO matches
grep -o 'style="[^"]*#[0-9a-fA-F]' dist/pg-dashboard.html
```

## Accessibility Testing

**Required for OpenAI store submission (compliance_master item 6).**

- [X] **Keyboard navigation**: all interactive elements reachable via Tab, activatable via Enter/Space
- [X] **Focus indicators**: visible focus ring on all focusable elements
- [X] **ARIA labels**: buttons, icons, and interactive elements have `aria-label` or visible text
- [X] **Color contrast**: text meets WCAG AA (4.5:1 for normal text, 3:1 for large text)
- [X] **No color-only indicators**: status/errors conveyed by more than color alone (icons, text)
- [X] **Readable text**: minimum 14px font size, adequate line spacing

### Widget a11y Tests

- [X] **Keyboard accessibility** (compliance #10): run `npm test` in widget-react, then perform full keyboard/manual audit
- [X] **Screen reader semantics/labels** (compliance #11): verify all interactive controls have proper ARIA attributes end-to-end

### Quick checks

```bash
# Check for missing aria-labels on buttons/icons in widget HTML
grep -E '<button[^>]*>' dist/pg-dashboard.html | grep -v 'aria-label'

# Check for images without alt text
grep -E '<img[^>]*>' dist/pg-dashboard.html | grep -v 'alt='
```

### Manual verification

1. Open widget in browser, unplug mouse
2. Tab through all interactive elements — verify focus order is logical
3. Activate buttons/links with Enter/Space — verify they work
4. Use browser dev tools accessibility panel to audit ARIA tree
5. Test with screen reader (VoiceOver on macOS: Cmd+F5)

## Hardcoded Values Scan

- [X] Scan codebase for hardcoded production domains that should use config
- [X] Check `redirect_domains`, `ui.domain`, webhook URLs use env-based config
- [X] Verify callback URLs and CORS are not hardcoded to your own domain/user
- [X] Verify no hardcoded API keys, secrets, or credentials
- [X] Docstring examples use placeholder domains (not real production URLs)

```bash
# Search for hardcoded production domains
grep -rn "priority-guard\.com" --include="*.py" backend/ mcp_server/ | grep -v test
grep -rn "onrender\.com" --include="*.py" backend/ mcp_server/ | grep -v test

# Check redirect_domains uses config variable
grep -rn "redirect_domains" mcp_server/
```

## MCP Server Connectivity

- [X]  `/.well-known/oauth-protected-resource` returns valid JSON
- [X] `/.well-known/oauth-authorization-server` returns valid JSON
- [X]  `HEAD /mcp` returns 200 (reachability probe)
- [X]  Tool calls work with valid JWT (test via MCP Inspector against production)

```bash
# Discovery endpoints
curl https://<MCP_SERVER>/\.well-known/oauth-protected-resource
curl https://<MCP_SERVER>/\.well-known/oauth-authorization-server

# Reachability probe
curl -I https://<MCP_SERVER>/mcp
```

## Latency Testing

**Tool calls must complete within 8 seconds (ChatGPT server-side timeout).**

### Priority Guardian

```bash
python ops/pg_latency_check.py
```

Tests infrastructure endpoints only (no auth required). For authenticated tool call latency, use MCP Inspector connected to production with a valid JWT.

### MindSort AI

```bash
# Infrastructure only (no auth required):
python ops/mindsort_latency_check.py

# Full test including authenticated tool calls:
MINDSORT_JWT=<your_token> python ops/mindsort_latency_check.py
```

The MindSort script tests both infrastructure and authenticated `load_saved_board` / `read_saved_board` calls. Write tools (`organize_thoughts`, `edit_board`, `start_prioritization_flow`, `delete_my_data`) are excluded from automated tests to avoid mutating the reviewer test account — test those manually in ChatGPT.

### Thresholds

| Latency | Infrastructure | Tool calls |
|---|---|---|
| Good | < 300ms | < 2000ms |
| Acceptable | 300–500ms | 2000–4000ms |
| Sluggish | 500–1000ms | 4000–8000ms |
| **TIMEOUT RISK** | > 1000ms | **> 8000ms — will fail in ChatGPT** |

### Checklist

- [ ] Each tool responds under 8s on first call (cold start)
- [ ] Each tool responds under 3s on subsequent calls (warm)
- [ ] Timeout error message is user-friendly, not stack trace
- [ ] No tools hang indefinitely under normal conditions

### Manual tool call timing (MindSort AI)

```bash
# Requires valid JWT from MCP Inspector or review account
TOKEN=<your_token>
MCP=https://priorities-guard-clarity-mcp.onrender.com

for tool in load_saved_board read_saved_board; do
  echo "Testing $tool..."
  time curl -s -X POST $MCP/mcp \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":{}}}" > /dev/null
done
```

### Common causes of timeout failures

- Render service on Free tier — spins down after 15 min inactivity → **upgrade to Hobby**
- Backend cold start behind the MCP server → check backend is also Hobby tier
- DB connection pool exhausted → check Render logs for connection errors
- JWKS fetch timeout on first request → JWKS cache not yet populated (warms on second call)

## Error Handling Audit

**Required for OpenAI store compliance (compliance_master item 10).**

Errors must be well-handled with clear messaging or fallback behavior across all layers.

### MCP Server Layer

- [X] Timeout protection on all backend HTTP calls (see per-app pattern below)
- [X] Timeout errors return clear user-facing message, not stack trace
- [X] Backend unreachable returns graceful error, not stack trace
- [X] Invalid/expired token returns `invalid_token` OAuth error (not 500)
- [X] Unknown tool returns `isError=True` with clear message
- [X] Bare `Exception` in dispatcher caught — returns generic user-friendly message

### Backend Layer

- [X] Global exception handler catches unhandled errors (`main.py` `global_exception_handler`)
- [X] Database errors logged but not exposed to user (no SQL in response — logs `error_type` only)
- [X] External API failures (Google, etc.) return user-friendly message — **N/A for MindSort AI** (no external API calls at backend layer)
- [X] OAuth errors follow RFC 6749 format (`error`, `error_description`)

### Widget Layer

- [X] React `ErrorBoundary` wraps `<App />` — catches render crashes, shows fallback UI
- [X] `loadError` state rendered as `role="alert"` div on tool output errors
- [X] Loading state before initialization — no blank state
- [X] Empty state when no clusters — clear message, not blank
- [X] Widget fallback HTML uses `var(--color-danger)` — shown if widget file fails to load

### Quick verification

#### Priority Guardian
```bash
# Verify PG tools use _call_with_timeout wrapper
grep -rn "_call_with_timeout" mcp_server/priority_guardian/tools/ | wc -l
# Expected: 15+ matches

# Verify widget has Error Boundary
grep -rn "class ErrorBoundary" mcp_server/priority_guardian/widget-react/src/main.tsx
# Expected: 1 match
```

#### MindSort AI
```bash
# MindSort AI uses asyncio.wait_for directly in persistence layer (not _call_with_timeout)
grep -rn "asyncio.wait_for" mcp_server/clarity/persistence.py
# Expected: 3 matches (persist_cluster, get_cluster, delete_cluster)

# Verify widget has Error Boundary
grep -rn "class ErrorBoundary" mcp_server/clarity/widget-react/src/main.tsx
# Expected: 1 match

# Verify fallback HTML uses CSS variable, not hardcoded hex
grep "WIDGET_FALLBACK_HTML" mcp_server/clarity/handlers/resources.py -A3
# Expected: var(--color-danger), not #dc2626
```

#### Both apps
```bash
# Check for bare except clauses (anti-pattern)
grep -rn "except:" --include="*.py" mcp_server/ backend/ | grep -v test
# Expected: 0 matches (all exceptions should be typed)
```

### Manual verification

**Only one manual test is realistically executable and worth doing:**

Use an expired or tampered JWT → call any tool via MCP Inspector → verify:
- Response contains `isError: true`
- Content text says "Authentication required. Please connect your account."
- `_meta["mcp/www_authenticate"]` is present in the response

This is the auth failure path reviewers will actually trigger. Everything else (backend 500, network disconnect) is either covered by the static code audit above or not meaningfully testable against a live production service.

---

## Data Minimization

> **Audit note (March 2026):** Items below reflect accurate status per codebase audit. Some items differ between apps — see per-app notes. None of the gaps below are OpenAI submission blockers; they are GDPR/best-practice items.

### Priority Guardian

- [X] OAuth scopes are minimal — `calendar.events.readonly` + `calendar.settings.readonly` only
- [X] Only essential user data is stored — priorities, deliverables, goals, weekly snapshots
- [X] Tokens/secrets scrubbed from logs (`logging.py` `scrub_sensitive_data` processor)
- [~] User IDs logged as full UUIDs (pseudonymous, not truncated — standard practice, acceptable)
- [X] Session tokens hashed before storage (`session_service.py`, `token_service.py`)
- [X] Board data deleted on `delete_my_data`; inactive accounts hard-deleted after 6 months (`retention_cleanup.py`)

### MindSort AI

- [ ] OAuth scopes minimal — **gap:** `clarity.write` is used for all operations including read-only (`load_saved_board`, `read_saved_board`). No `clarity.read` scope exists. Single-scope design is a deliberate simplification but does not satisfy "read-only where possible." Post-launch improvement: add `clarity.read` scope for read-only tools.
- [~] Only essential user data stored — data model is lean (single snapshot per user, deprecated fields not persisted). However `cluster_data` stores full freeform thought content which may include sensitive personal information. Shared auth layer adds consent/audit/session records. Acceptable but not unconditionally clean.
- [X] Tokens/secrets scrubbed from logs (`logging.py` `scrub_sensitive_data` processor) ✅
- [~] User IDs logged as full UUIDs throughout (`clusters_router.py`, `token_service.py`, `mcp_auth.py`). Pseudonymous identifiers — standard practice, not truncated. Checklist wording "truncated" was inaccurate.
- [X] Session tokens hashed before storage — refresh tokens encrypted + hashed (`token_service.py`); access token JTI only stored, not plaintext
- [~] Data retained after OAuth revocation by design (`revoke.py` explicitly does not delete board data or browser sessions — preserves cross-app identity). Board data deleted via `delete_my_data` tool or 6-month inactive account cleanup (`retention_cleanup.py`). Intentional design decision; disclose retention period in privacy policy.

### Both apps

- [X] No API keys, credentials, or secrets in logs
- [X] Audit logs hard-deleted after 90 days (`retention_cleanup.py` `cleanup_expired_audit_logs`)
- [X] No unnecessary data retained — inactive accounts deleted after 6 months with cascade


## Post-Deploy Smoke Test

After deploying to production but before submitting:

1. Open ChatGPT with the app connected
2. Trigger each tool at least once
3. Verify widget renders (inline and fullscreen)
4. Verify OAuth connect/disconnect flow
5. Verify data persists across conversations
6. Test on mobile (ChatGPT iOS app)

## Text Scaling Test (OpenAI UI Guideline #13)

OpenAI requires the widget layout to not break when users increase browser font size.

- [X] Widget tested at default, large, and very large font sizes
- [X] No text overflow, clipping, or broken layout at any size
- [X] Tested on mobile at iOS largest accessibility font size

### How to test — desktop

1. Open the widget in Chrome (served locally or via production URL)
2. Chrome Settings → Appearance → **Font size** → test at: Medium → Large → Very Large
3. Alternatively paste into Chrome DevTools Console:
```javascript
   document.body.style.fontSize = '20px'  // Large
   document.body.style.fontSize = '24px'  // Very Large
   document.body.style.fontSize = ''      // Reset
```
4. At each size verify:
   - [X] No text overflows or gets clipped in any container
   - [X] No buttons or interactive elements overlap or disappear
   - [X] No horizontal scrollbar appears inside the widget
   - [X] Priority names, deliverable text, goal text wrap cleanly
   - [X] Hour targets and actual values remain readable
   - [X] Weekly report pie chart labels do not overflow

### How to test — mobile (iOS)

1. iOS Settings → Accessibility → Display & Text Size → **Larger Text** → drag to maximum
2. Open ChatGPT iOS app → trigger widget
3. Apply same checks as desktop above

**Pass criteria:** Widget fully readable and usable at all font sizes. No clipped content, no broken layout.

On WCAG AA specifically: Given you're using Apps SDK UI system tokens throughout, you almost certainly pass for the main content. The only risk areas to eyeball are secondary/tertiary text (the greyed-out supporting text under priority names) and any status colors (the colored left borders on P1/P2/P3). Check those two things visually and you're done.

---

## Pre-Submission: Production Redirect URI (B2-8)

**Status: ✅ DONE** (06 March 2026)

ChatGPT assigns a unique `callback_id` per connector (e.g., `YBf91qGED3L6`). Rather than hardcoding each callback_id, we use **prefix matching** to accept any callback_id under the `/connector/oauth/` path.

**Implementation:**

Allowlist entries ending with `/` are treated as prefix matches. This allows dynamic callback IDs without code changes per connector.

```python
_CHATGPT_REDIRECT_URIS: ClassVar[list[str]] = [
    "https://chatgpt.com/connector/oauth/",  # prefix — any connector callback_id
    "https://chatgpt.com/connector_platform_oauth_redirect",  # legacy (exact match)
    "https://platform.openai.com/apps-manage/oauth",  # review (exact match)
]
```

**How prefix matching works:**

- `https://chatgpt.com/connector/oauth/YBf91qGED3L6` → ✅ matches prefix
- `https://chatgpt.com/connector/oauth/ABC123` → ✅ matches prefix
- `https://chatgpt.com/connector_platform_oauth_redirect` → ✅ exact match
- `https://evil.com/connector/oauth/ABC123` → ❌ rejected (wrong host)

**Validation:**

- Unit tests: `tests/unit/oauth_provider/test_b2_compliance_unit.py::TestRedirectURIPrefixMatching`
- Validator: `backend/core/oauth_provider/validators/client_metadata.py`

**Compliance reference:** `compliance_master_1.3.26.md` B2-8
