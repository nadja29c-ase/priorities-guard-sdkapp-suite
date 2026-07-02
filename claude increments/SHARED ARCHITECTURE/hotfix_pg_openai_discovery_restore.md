# Hotfix: Restore PG-OpenAI discovery to pre-5854d50 working shape (production incident)

**Type:** Production rollback hotfix. PG-OpenAI MCP service ONLY (`pg.priority-guard.com`). NOT architecture work — restores a previously-approved, previously-working discovery configuration.

**Severity:** High — PG (live in ChatGPT App Store) silently fails to connect/reconnect in production.

**Date:** 2026-06-30.

---

## Symptom
ChatGPT PG connector: OAuth completes (consent shown, code issued, token issued with correct `iss`/`aud`), ChatGPT returns to the connector tile, tile stays **"Connect"** — never reaches connected state. No error shown. Critically: **no authenticated `POST /mcp`** ever appears in the PG MCP logs after token issuance — ChatGPT obtains a valid token and silently abandons before calling the resource server.

## Confirmed root cause
Commit **`5854d50`** ("Fix AS discovery: all endpoints point to www") changed `mcp_server/priority_guardian/discovery.py`, moving `token_endpoint` / `jwks_uri` / `registration_endpoint` AND `authorization_servers` from the MCP origin (`pg.priority-guard.com`, `MCP_SERVER_URL`) to the backend root (`www.priority-guard.com`, `OAUTH_ISSUER_BASE`).

This broke the **same-origin token-exchange chain** ChatGPT depends on. ChatGPT's MCP OAuth flow:
1. Reads protected-resource metadata → `authorization_servers`.
2. Fetches `<authorization_servers[0]>/.well-known/oauth-authorization-server`.
3. Performs token / jwks / register against the endpoints in that AS metadata.
4. Calls `/mcp` with the bearer token.

The working (pre-regression) design served those token/jwks/register endpoints on the SAME origin ChatGPT discovered (`pg.priority-guard.com`, via the proxy routes in `server.py`). The regression pointed them at a DIFFERENT origin (`www`) than the advertised `authorization_servers`, so ChatGPT could not complete the discovery→token association coherently and abandoned silently between step 3 and step 4 — exactly matching "token issued, no `/mcp` call, tile stays Connect."

### Evidence (production curls + git)
- `pg.../.well-known/oauth-protected-resource` advertised `authorization_servers: ["https://www.priority-guard.com"]` (root).
- `www.../.well-known/oauth-authorization-server` resolves, but its endpoints are `www/oauth/pg/*` — a different origin than the RS.
- `www/oauth/pg/.well-known/oauth-authorization-server` → **404** (backend serves AS metadata at root only).
- MindSort-OpenAI (works) advertises `["https://www.priority-guard.com/oauth/mindsort"]` and its `www/oauth/mindsort/.well-known/oauth-authorization-server` **resolves** — an app-specific chain PG lacked.
- `git show 5854d50~1:.../discovery.py` revealed the working shape was deliberately **mixed-origin** (see below). The regression "consolidated" it to all-www and broke it.

### Why the working shape is mixed-origin (and correct)
```
issuer                = https://www.priority-guard.com            # matches token iss claim (backend mints iss=www)
authorization_endpoint= https://www.priority-guard.com/oauth/pg/authorize  # browser popup, no same-origin constraint; backend serves HTML correctly
token_endpoint        = https://pg.priority-guard.com/oauth/token     # same-origin proxy route (server.py)
jwks_uri              = https://pg.priority-guard.com/oauth/jwks       # same-origin proxy route
registration_endpoint = https://pg.priority-guard.com/oauth/register  # same-origin proxy route
authorization_servers = [https://pg.priority-guard.com]               # ChatGPT discovers AS at the RS origin
```
This satisfies BOTH constraints simultaneously: (a) ChatGPT's same-origin discovery→token/jwks/register behavior, and (b) token `iss`=www matching (issuer field stays www). The "consistency fix" in 5854d50 sacrificed (a) to tidy (b), not realizing (a) was load-bearing.

## Fix applied
Restored `mcp_server/priority_guardian/discovery.py` to its exact pre-`5854d50` content (the approved, previously-working shape), with an added NOTE block documenting the incident so the mixed-origin design is not "consolidated" again. **Change verified on disk.**

Scope of change: **`mcp_server/priority_guardian/discovery.py` only.**
- Backend: NOT touched.
- PG-Claude (`mcp_server/priority_guardian_claude/`, `_dupl` files): NOT touched — Claude uses root issuer by design (inc_05). The Claude/OpenAI adapter separation is exactly why this fix is safe to make on the OpenAI side alone.
- MindSort (`mcp_server/clarity/`): NOT touched — works as-is.

The proxy routes the restored discovery points at (`/oauth/token`, `/oauth/jwks`, `/oauth/register` on the MCP origin) still exist in current `server.py` — the infrastructure the working version depended on is intact; only the discovery values had drifted.

## Pre-deploy
- [ ] Read `OPERATIONS_PREDEPLOY.md` (MCP-service deploy).
- [ ] Grep for any test asserting the post-regression all-www discovery shape (would now fail and need updating to the restored shape): `mcp_server/priority_guardian/tests/` and any discovery/oauth test referencing `oauth_authorization_server` / `oauth_protected_resource` / `authorization_servers`. If found, update expectations to the restored mixed-origin shape; if none, note that.

## Deploy
Redeploy the **PG-OpenAI MCP service** (`pg.priority-guard.com` / Render `priority-guardian-mcp`). NOT the backend.

## Post-deploy verification (the real proof — do all)
1. `curl https://pg.priority-guard.com/.well-known/oauth-protected-resource` → `authorization_servers` is `["https://pg.priority-guard.com"]`.
2. `curl https://pg.priority-guard.com/.well-known/oauth-authorization-server` → `token_endpoint`/`jwks_uri`/`registration_endpoint` are `https://pg.priority-guard.com/oauth/*`; `issuer` is `https://www.priority-guard.com`.
3. Clean ChatGPT PG reconnect, watch PG MCP logs for the chain that was missing:
   - `oauth.token.success` (backend) → **authenticated `POST /mcp`** on `pg.priority-guard.com` → `auth.success` → tile **Connected**.
4. Regression check: MindSort-OpenAI still connects (untouched, but confirm shared nothing broke).

Interpretation:
- Authenticated `/mcp` now appears + tile Connected → incident resolved.
- Token still issued but still no `/mcp` call → the discovery shape is still not what ChatGPT needs; re-curl and compare byte-for-byte against MindSort's working chain before any further change. Do NOT iterate blindly.

## Relationship to other work
- **Independent of `inc_token_rate_limit_raise`.** The token 429 was a real, separate bug (still worth shipping), but THIS discovery regression is what broke connect — proven by the attempt showing `oauth.token.success` with no `/mcp` call. Ship both; this one fixes "PG won't connect."
- **Not inc_08.** inc_08 (consent classification) works end-to-end in the same logs.

## Frozen-approval note
PG-OpenAI is the approved/frozen App Store version. This change **restores** previously-approved discovery output rather than inventing a new shape, which is the lowest-risk action. Discovery metadata is runtime infra (not the reviewed manifest), so restoring the working shape is not expected to require re-review — but that is an OpenAI-platform question, not a code one.

## Lesson
Every time this incident was debugged from a summary (git log, truncated diff), the proposed fix was wrong (`/oauth/pg` → 404; `[MCP_SERVER_URL]`-alone → re-breaks on issuer/endpoint origin). Every time it was debugged from the actual artifact (full pre-regression file, production curls), it was right. For discovery/OAuth changes: read the actual served document and the actual file at the working commit; do not act on summaries. And "spec-consistency cleanups" to working OAuth discovery are high-risk — ChatGPT's real behavior, not RFC tidiness, is the constraint.
