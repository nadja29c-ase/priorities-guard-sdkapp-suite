# Pre-Submission Operations Checklist

Run through this checklist before submitting any SDK app to the OpenAI store.

## Render Environment

- [ ] **ENV=production** on Render for ALL services (backend, MCP servers)
- [ ] Verify: `ENV` is not `dev`, `development`, or `local` on any production service
- [ ] All `required=True` config values have env vars set (will fail-fast at startup if missing)
- [ ] `INTERNAL_API_SECRET` set and matching between backend and MCP server(s)
- [ ] `CORS_ALLOWED_ORIGINS` explicitly set (required in production)
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

# Clarity MCP — should return {"status": "ok", ...}
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

- [ ] Widget built and HTML copied to `widgets/` directory
- [ ] Built HTML is the production build (not dev mode)
- [ ] No `style=` attributes containing hardcoded hex colors (run grep check below)

```bash
# Should return NO matches
grep -o 'style="[^"]*#[0-9a-fA-F]' dist/pg-dashboard.html
```

## Accessibility Testing

**Required for OpenAI store submission (compliance_master item 6).**

- [ ] **Keyboard navigation**: all interactive elements reachable via Tab, activatable via Enter/Space
- [ ] **Focus indicators**: visible focus ring on all focusable elements
- [ ] **ARIA labels**: buttons, icons, and interactive elements have `aria-label` or visible text
- [ ] **Color contrast**: text meets WCAG AA (4.5:1 for normal text, 3:1 for large text)
- [ ] **No color-only indicators**: status/errors conveyed by more than color alone (icons, text)
- [ ] **Readable text**: minimum 14px font size, adequate line spacing

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

- [ ] Scan codebase for hardcoded production domains that should use config
- [ ] Check `redirect_domains`, `ui.domain`, webhook URLs use env-based config
- [ ] Verify no hardcoded API keys, secrets, or credentials
- [ ] Docstring examples use placeholder domains (not real production URLs)

```bash
# Search for hardcoded production domains
grep -rn "priority-guard\.com" --include="*.py" backend/ mcp_server/ | grep -v test
grep -rn "onrender\.com" --include="*.py" backend/ mcp_server/ | grep -v test

# Check redirect_domains uses config variable
grep -rn "redirect_domains" mcp_server/
```

## MCP Server Connectivity

- [ ] `/.well-known/oauth-protected-resource` returns valid JSON
- [ ] `/.well-known/oauth-authorization-server` returns valid JSON
- [ ] `HEAD /mcp` returns 200 (reachability probe)
- [ ] Tool calls work with valid JWT (test via MCP Inspector against production)

```bash
# Discovery endpoints
curl https://<MCP_SERVER>/\.well-known/oauth-protected-resource
curl https://<MCP_SERVER>/\.well-known/oauth-authorization-server

# Reachability probe
curl -I https://<MCP_SERVER>/mcp
```

## Latency Testing

**Tool calls must complete within 8 seconds (TIMEOUT_S in mcp_auth.py).**

- [ ] Each tool responds under 8s on first call (cold start)
- [ ] Each tool responds under 3s on subsequent calls (warm)
- [ ] Timeout error message is user-friendly, not stack trace
- [ ] No tools hang indefinitely under normal conditions

```bash
# Measure tool latency (requires valid JWT)
time curl -X POST https://<MCP_SERVER>/mcp \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "<TOOL_NAME>", "arguments": {}}}'

# Check multiple tools in sequence
for tool in get_today get_week get_patterns; do
  echo "Testing $tool..."
  time curl -s -X POST https://<MCP_SERVER>/mcp \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d "{\"method\": \"tools/call\", \"params\": {\"name\": \"$tool\", \"arguments\": {}}}" > /dev/null
done
```

## Data Minimization

- [ ] OAuth scopes are minimal (read-only where possible, no unnecessary permissions)
- [ ] Only essential user data is stored in database
- [ ] Logs do not contain PII (user IDs truncated, no tokens/secrets)
- [ ] Session tokens hashed before storage
- [ ] No unnecessary data retained after user disconnects

## Submission Artifacts

- [ ] ANNOTATION_JUSTIFICATIONS.md created (one entry per tool annotation)
- [ ] Screenshots: inline card + fullscreen, light mode + dark mode
- [ ] Support email configured in store listing
- [ ] Privacy policy URL accessible and accurate
- [ ] App name and description finalized

## Post-Deploy Smoke Test

After deploying to production but before submitting:

1. Open ChatGPT with the app connected
2. Trigger each tool at least once
3. Verify widget renders (inline and fullscreen)
4. Verify OAuth connect/disconnect flow
5. Verify data persists across conversations
6. Test on mobile (ChatGPT iOS app)
