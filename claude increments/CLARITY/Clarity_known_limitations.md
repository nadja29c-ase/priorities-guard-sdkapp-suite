# Clarity — Known Limitations - MIGHT BE OUTDATED!

Technical documentation of known limitations, their root causes, and potential future solutions.

---

## 1. Cross-Browser/Device Data Loss

### Problem

User data is lost when disconnecting and reconnecting from a different browser or device.

### User Scenarios That Lose Data

| Scenario | Result |
|----------|--------|
| Connect on laptop, disconnect on phone, reconnect on phone | ❌ Data lost |
| Connect in Chrome, disconnect in Firefox, reconnect in Firefox | ❌ Data lost |
| Clear browser cookies, reconnect | ❌ Data lost |
| Reconnect from work computer (different browser) | ❌ Data lost |
| Reconnect from same browser (cookies intact) | ✅ Data preserved |

### Root Cause

**ChatGPT stores OAuth tokens server-side per ChatGPT account, not per browser.**

Identity resolution chain during OAuth authorization:
1. `login_hint` parameter → find user by `chatgpt_user_id` — **OpenAI does not send this**
2. `pg_session` cookie → find user by browser session — **Only works in same browser**
3. Neither → create new anonymous user — **Data orphaned**

```
Disconnect (any browser)
    ↓
Reconnect (different browser)
    ↓
No cookie (different browser) + No login_hint (OpenAI doesn't send)
    ↓
New anonymous user created
    ↓
New token issued for new user
    ↓
ChatGPT stores new token server-side
    ↓
ALL browsers now use new token
    ↓
Original user's data orphaned
```

### Why Cookie Alone Isn't Enough

The `pg_session` cookie is set on `priority-guard.com` during OAuth consent. It only exists in the browser where the user first connected. ChatGPT opens OAuth in a popup from `chatgpt.com`, so:

- Cookie is first-party to our domain (not blocked)
- But only exists in the original browser
- Other browsers/devices have no way to identify the user

### Why `login_hint` Would Fix This

If ChatGPT sent `login_hint` (a pseudonymous user ID) during OAuth authorization:
- We could find/create user by `chatgpt_user_id`
- Same ChatGPT account = same user, regardless of browser
- This is standard OAuth practice, but OpenAI hasn't implemented it

### Current Mitigation

1. **User warning on consent screen** — Tell users to reconnect from same browser
2. **Helpful message when data appears lost** — Explain possible cause
3. **Manual data recovery** — Admin can migrate clusters between users via SQL

### Future Solutions

| Solution | Effort | Notes |
|----------|--------|-------|
| Wait for OpenAI `login_hint` | None | Out of our control |
| Manual account linking (one-time code) | Half day | User-initiated, reliable |
| "Recover my data" admin tool | 2 hours | Temporary workaround |

### Manual Data Recovery (Admin)

```sql
-- 1. Find the user with orphaned clusters
SELECT u.id, u.created_at, c.created_at as cluster_updated
FROM core_users u
JOIN clarity_clusters c ON c.user_id = u.id
ORDER BY c.created_at DESC;

-- 2. Find the user's current (new) user ID
-- (Check latest oauth_access_tokens or ask user to call get_my_clusters)
SELECT user_id, created_at 
FROM oauth_access_tokens 
ORDER BY created_at DESC 
LIMIT 1;

-- 3. Migrate clusters to new user
UPDATE clarity_clusters 
SET user_id = '<new-user-id>'
WHERE user_id = '<old-user-id>';
```

---

## 2. OpenAI Safety Filter False Positives

### Problem

OpenAI's safety classifier occasionally blocks widget rendering for benign content.

### Symptoms

- Tool call succeeds (200 response)
- Data persisted to database
- Widget does not render
- ChatGPT shows: "This tool call was blocked by OpenAI because we couldn't determine the safety status of the request."

### Root Cause

OpenAI's client-side safety filter runs AFTER our server responds. It can block rendering based on:
- Content heuristics (unknown triggers)
- Non-deterministic classifier behavior
- No way to appeal or debug

### Example Blocked Content (False Positive)

```
"Prepare and send invoices for completed milestones"
"Follow up on overdue payments"
```

Likely trigger: financial keywords like "invoices" and "payments".

### What We Control

| Layer | Control | Status |
|-------|---------|--------|
| Tool response | ✅ Yes | Data persisted before response |
| Widget rendering | ❌ No | OpenAI client controls |
| Error message | ❌ No | OpenAI client controls |
| Retry logic | ❌ No | OpenAI client controls |

### Current Mitigation

1. **Data always persisted first** — User data is never lost, only display is blocked
2. **Rich text fallback** — `content` field includes cluster summary (if text passes but widget blocked)
3. **Idempotent design** — Retry is always safe

### Future Solutions

None available. This is platform risk. OpenAI's safety system is a black box.

---

## 3. ChatGPT Schema Errors

### Problem

ChatGPT occasionally sends malformed payloads that don't match the tool schema.

### Examples

| Error | ChatGPT Sent | Expected |
|-------|--------------|----------|
| Invalid tag | `"tags": ["maintain"]` | Tags must be from allowed list |
| Missing required field | No `thoughts_exhausted` | Required boolean |
| Wrong structure | Raw string array | Cluster objects |

### Current Mitigation

LLM error compensation in `cluster_raw_thoughts.py`:
- Strip invalid tags (continue with valid ones)
- Default `thoughts_exhausted` to `false` if missing
- Attempt to repair malformed structures
- Only reject if completely unparseable

### Status

Mostly handled. Repair logic covers common cases.

---

## 4. Two-Tool Chaining Failures

### Problem

ChatGPT sometimes fails to complete the two-tool workflow (`get_my_clusters` → `cluster_raw_thoughts`) in a single turn.

### Symptoms

- ChatGPT calls `get_my_clusters`, gets historical data
- ChatGPT responds to user with text instead of calling `cluster_raw_thoughts`
- User sees no widget, has to prompt again

### Root Cause

Tool description wasn't explicit enough about chaining requirement.

### Current Mitigation

Updated tool descriptions with explicit workflow:

```
═══════════════════════════════════════════════════════════════════════════════
CRITICAL: TWO-TOOL CHAINING WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

BOTH CALLS HAPPEN IN ONE TURN. Do NOT respond to user between calls.

CORRECT FLOW:
1. Call get_my_clusters → receive historical clusters
2. Merge new user thoughts with historical clusters
3. Call cluster_raw_thoughts with the COMPLETE merged set
4. THEN respond to user with the widget

WRONG FLOW:
1. Call get_my_clusters → receive historical clusters
2. Respond to user with text ← WRONG
```

### Status

Improved. Still dependent on ChatGPT following instructions.

---

## 5. Stale Session ID After Deploy (FIXED)

### Problem

FastMCP stored session IDs in memory. Server restart = sessions lost. ChatGPT sent stale session ID → 400 error.

### Solution

Added `stateless_http=True` to FastMCP initialization:

```python
mcp = FastMCP("clarity-mcp", streamable_http_path="/mcp", stateless_http=True)
```

Each request is now self-contained, authenticated via JWT. No session state required.

### Status

✅ Fixed in Increment 11.

---

## 6. Post-Launch Hardening: Transport-Layer OAuth Gaps (Deferred)

Two related transport-layer gaps that do not affect ChatGPT in production but leave the implementation technically incomplete. To be fixed together in a single post-launch increment.

### Gap A: HTTP-Layer 401 + WWW-Authenticate Missing on /mcp (B2-7)

The OpenAI Apps SDK spec (B2-7) requires the MCP server to return HTTP 401 with a `WWW-Authenticate` header when token verification fails on `/mcp`. Currently auth failures return errors via the JSON-RPC body with `_meta["mcp/www_authenticate"]` (B2-10) — no HTTP-layer 401 is set.

**Why not a submission blocker:** ChatGPT's OAuth UI trigger relies on `_meta["mcp/www_authenticate"]` (B2-10), which is implemented. Discovery works via `/.well-known/oauth-protected-resource`. Auth flow works end-to-end.

**Why still a real gap:** Spec uses "must" language. Non-ChatGPT OAuth clients may depend on HTTP-layer 401.

**Planned fix:** Add `WWWAuthenticateMiddleware` to both MCP servers. Buffers `/mcp` POST response, detects `isError: true` + `mcp/www_authenticate` in JSON body, rewrites HTTP status to 401 with `WWW-Authenticate` header.

### Gap B: CORS Missing on `/.well-known/*` Discovery Endpoints

`CORSMiddleware` is added to `fastmcp_app` but does NOT propagate to the mounted `discovery_app` sub-app — this is a known Starlette behaviour. As a result, `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`, and `/.well-known/openid-configuration` return no CORS headers on preflight requests.

**Why not a submission blocker:** ChatGPT makes server-side requests — no CORS enforcement. Discovery endpoints work correctly for ChatGPT. PG shipped to production with the same gap.

**Why still a real gap:** Any browser-based OAuth client (MCP Inspector, future tooling, OpenAI tooling changes) will fail to discover OAuth metadata. Discovery endpoints are architecturally broken for browser contexts.

**Confirmed symptom:** MCP Inspector OAuth flow fails with "Failed to discover OAuth metadata" — root cause is this CORS gap, not routing or DNS.

**Planned fix:** Add `CORSMiddleware` with `allow_origins=["*"]` directly to `discovery_app` in both `mcp_server/clarity/server.py` and `mcp_server/priority_guardian/server.py`. Discovery docs are public by spec (RFC 8414, RFC 9728) — `*` is correct and intentional.

```python
discovery_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)
```

### Applies To

Both MindSort AI and Priority Guardian — identical gaps in both servers.

---

## Summary

| Limitation | Severity | User Impact | Fix Available |
|------------|----------|-------------|---------------|
| Cross-browser data loss | High | Data orphaned | Partial (warning) |
| Safety filter false positives | Medium | Widget blocked | None |
| Schema errors | Low | Handled | ✅ Repair logic |
| Two-tool chaining | Medium | Extra prompt needed | ✅ Better descriptions |
| Stale session ID | N/A | N/A | ✅ Fixed |
| B2-7 HTTP 401 on /mcp | Low | None in practice | Deferred post-launch |
| CORS on discovery endpoints | Low | None in practice (ChatGPT) | Deferred post-launch |

---

*Last updated: March 2026*
