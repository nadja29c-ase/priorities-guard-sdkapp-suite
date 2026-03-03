# Pre-Submission Operations Checklist

Run through this checklist before submitting any SDK app to the OpenAI store.

## Render Environment

- [ ] **ENV=production** on Render for ALL services (backend, MCP servers)
- [ ] Verify: `ENV` is not `dev`, `development`, or `local` on any production service
- [ ] All `required=True` config values have env vars set (will fail-fast at startup if missing)
- [ ] `INTERNAL_API_SECRET` set and matching between backend and MCP server(s)
- [ ] `CORS_ALLOWED_ORIGINS` explicitly set (required in production)

## Domain / ui.domain Verification

**This is the #1 cause of "unable to connect" rejections.**

- [ ] `ui.domain` in `_meta` matches the actual MCP server origin that OpenAI will reach
- [ ] Verify dynamically: `ui.domain` must come from env var via `_extract_origin()`, NOT hardcoded
- [ ] Hit the MCP server URL in browser — confirm it resolves and returns health check
- [ ] No path component in `ui.domain` (pure origin only: `https://host.com`, not `https://host.com/mcp`)

### Per-app verification commands

```bash
# PG MCP — should return {"status": "ok", ...}
curl https://pg-mcp.priority-guard.com/

# Clarity MCP — should return {"status": "ok", ...}
curl https://priorities-guard-clarity-mcp.onrender.com/
```

Cross-check: the origin from `curl` must match what the app returns in `_meta.ui.domain` at runtime.

### Known issue (fixed)

Clarity previously hardcoded `"https://clarity.priority-guard.com"` as `ui.domain` while the MCP server ran at `https://priorities-guard-clarity-mcp.onrender.com`. This caused submission rejection. Fix: use `_extract_origin(MCP_SERVER_URL)` pattern (same as PG).

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
