# Claude Code Briefing: Increment 09 — Clarity OAuth Scope Integration

## Context

Clarity MCP server is deployed and reachable. ChatGPT completes OAuth flow and sends valid JWT tokens. However, tokens contain only Focused scopes (`focused.read`, `focused.write`, `focused.notify`). Clarity requires `clarity.write` scope, resulting in `-32003 Forbidden` errors.

The OAuth provider is **shared** across all Priority Guardian apps (`/oauth/pg/*`). Clients register once and can request any combination of supported scopes.

## Problem Statement

ChatGPT's OAuth client was registered before Clarity existed. The client's allowed scopes don't include `clarity.write`, so:

1. Authorization endpoint rejects `scope=clarity.write` requests ("Requested scopes exceed client's registered scopes")
2. Existing tokens lack `clarity.write`
3. Consent UI has no description for `clarity.write`

## Success Criteria

- [ ] OAuth provider advertises `clarity.write` in discovery (`scopes_supported`)
- [ ] OAuth provider accepts `clarity.write` at `/authorize` endpoint
- [ ] OAuth provider includes `clarity.write` in issued tokens (`scope` claim)
- [ ] Consent UI displays localized description for `clarity.write`
- [ ] Existing OAuth clients can be updated to include `clarity.write`
- [ ] New clients can register with `clarity.write` scope
- [ ] Clarity MCP accepts tokens containing `clarity.write` scope

## Technical Requirements

### 1. Discovery Endpoint

File: `backend/core/oauth_provider/discovery.py`

Verify `clarity.write` is present in `scopes_supported` array. If missing, add it.

```python
"scopes_supported": [
    "focused.read",
    "focused.write", 
    "focused.notify",
    "clarity.write"  # Must be present
]
```

### 2. Authorization Endpoint Scope Validation

File: `backend/core/oauth_provider/authorize.py`

The authorize endpoint validates requested scopes against:
1. Provider's supported scopes (implicit — if not in discovery, rejected)
2. Client's registered scopes (explicit check in code)

Verify both checks pass for `clarity.write`. The current code validates against `client.scopes` — this is correct behavior.

### 3. Consent UI Scope Descriptions

File: `backend/core/oauth_provider/authorize.py`

Add `clarity.write` to both scope description dictionaries:

**English:**
```python
"clarity.write": "Organize and cluster your thoughts into visual groups."
```

**German:**
```python
"clarity.write": "Deine Gedanken in visuelle Gruppen organisieren und clustern."
```

### 4. Token Endpoint Scope Issuance

File: `backend/core/oauth_provider/token_endpoint.py` (or related service)

Verify the token endpoint includes requested scopes in the issued JWT's `scope` claim. This should already work if the authorization flow accepts the scope — confirm no filtering occurs at token issuance.

### 5. Client Scope Storage Update

**First:** Identify where OAuth client registrations and their allowed scopes are stored. Check:
- `core_connections` table with `connection_type = 'oauth_provider'`
- Dedicated `oauth_clients` table (if exists)
- Model: `CoreConnection` or similar

**Then:** Provide mechanism to add `clarity.write` to existing clients:

**Option A: SQL migration script** (for existing production clients)

File: `scripts/add_clarity_scope_to_clients.sql`

```sql
-- Verify table structure first
-- UPDATE <oauth_clients_table>
-- SET scopes = array_append(scopes, 'clarity.write')
-- WHERE <client_identifier>
--   AND NOT ('clarity.write' = ANY(scopes));
```

**Option B: Admin endpoint** (if update mechanism exists)

Document the API call or admin action required.

### 6. No MCP Server Changes Required

Clarity's `mcp_auth.py` already enforces `clarity.write` correctly via `TOOL_SCOPES`. No changes needed.

## Files to Modify

```
backend/core/oauth_provider/discovery.py      — Verify/add clarity.write to scopes_supported
backend/core/oauth_provider/authorize.py      — Add scope descriptions (EN + DE)
scripts/add_clarity_scope_to_clients.sql      — One-time client update script (new file)
```

## Files to Reference (Read-Only)

```
backend/core/oauth_provider/register_client.py   — Client registration logic
backend/core/oauth_provider/token_endpoint.py    — Token issuance logic
backend/core/oauth_provider/services/           — Service layer for OAuth
backend/core/models.py                          — Database models (find OAuth client storage)
mcp_server/clarity/config.py                    — TOOL_SCOPES definition
```

## Constraints

- No breaking changes to existing Focused OAuth flows
- Existing Focused tokens must continue working
- GDPR: No new PII collection (scope is not PII)
- Backwards compatible: clients without `clarity.write` continue working for Focused-only use

## Unit Tests

File: `tests/unit/oauth_provider/test_clarity_scope.py`

| Test | Assertion |
|------|-----------|
| `test_scope_descriptions_include_clarity_write_en` | EN dict contains `clarity.write` key |
| `test_scope_descriptions_include_clarity_write_de` | DE dict contains `clarity.write` key |
| `test_clarity_scope_descriptions_not_empty` | Both descriptions are non-empty strings |

## Integration Tests

File: `tests/integration/oauth_provider/test_clarity_scope_integration.py`

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_discovery_includes_clarity_write` | GET `/.well-known/openid-configuration` | `clarity.write` in `scopes_supported` |
| `test_register_client_with_clarity_scope` | POST `/oauth/pg/register` with `scope: "clarity.write"` | 201, client created with scope |
| `test_authorize_accepts_clarity_scope` | Register client with `clarity.write`, GET `/oauth/pg/authorize?scope=clarity.write&...` | 200, consent page rendered |
| `test_authorize_rejects_unregistered_scope` | Client with only `focused.*`, request `scope=clarity.write` | `invalid_scope` error redirect |
| `test_token_includes_clarity_scope` | Complete full OAuth flow with `clarity.write` | Decoded JWT `scope` claim contains `clarity.write` |

## Out of Scope

- Multi-app consent UI redesign
- Scope grouping/categorization by app
- Automatic scope migration for all existing clients
- Changes to Clarity MCP server auth logic

## Deployment Steps

1. Deploy backend with updated code
2. Verify discovery endpoint returns `clarity.write` in `scopes_supported`
3. Run client scope update script against production DB (if updating existing clients)
4. Instruct users to disconnect/reconnect MCP server in ChatGPT to trigger re-authorization

## Verification Checklist

After deployment, verify end-to-end:

| Step | Check | Expected Result |
|------|-------|-----------------|
| 1 | GET `/.well-known/openid-configuration` | `clarity.write` in `scopes_supported` |
| 2 | Register new client with `clarity.write` | 201 success |
| 3 | Start OAuth flow with `scope=clarity.write` | Consent page shows Clarity description |
| 4 | Complete OAuth flow | Token issued |
| 5 | Decode issued JWT | `scope` claim contains `clarity.write` |
| 6 | Call Clarity `cluster_raw_thoughts` tool | No `-32003 Forbidden` error |
| 7 | Check Render logs | `scope.enforcement.success tool=cluster_raw_thoughts` |

## Notes

- Error progression: `Invalid issuer` → `Forbidden missing scope` confirms JWT validation works; only scope is missing
- ChatGPT reuses existing tokens until re-auth; user MUST disconnect/reconnect
- Provider behavior: "reject requested scopes not in client's allowed list" is correct and must be preserved