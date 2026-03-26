# Increment 07: Clarity OAuth Production Hardening

## Context

OAuth is implemented and tested with mocked JWT validation. Three gaps remain before production: no handler-level test for unknown tools, no test verifies internal API security, and no test uses real JWKS fetch.

**Note:** ChatGPT MCP marketplace does not exist yet. Users connect via manual URL in Developer Mode. No connector registration or `azp` validation required.

## Current State

| Item | Status |
|------|--------|
| Unknown tool fails closed (unit tests) | ✅ Done |
| Unknown tool fails closed (handler-level) | ❌ Missing |
| JWT validation logic | ✅ Done |
| Scope enforcement | ✅ Done |
| Discovery endpoint | ✅ Done |
| Unit tests (mocked) | ✅ Done (40+ tests) |
| Internal secret enforcement test | ❌ Missing |
| E2E test with real JWKS | ❌ Missing |
| Deployment docs | ❌ Missing |

## Blocking Items

### 1. Handler-Level Unknown Tool Test

**Why:** Existing unit tests call `authenticate_request()` directly. No test proves the full dispatcher path rejects unknown tools.

**File:** `tests/integration/clarity/test_tool_dispatcher.py`

**Test requirements:**
- Unknown tool name → returns error result
- Unknown tool → persistence never called
- Typo in tool name (e.g., `cluster_raw_thought`) → returns error

**Note:** If tests fail, fix at dispatcher level with proper error type (`UnauthorizedError` or dedicated error, NOT `InsufficientScopeError`).

### 2. Internal Secret Enforcement Test

**Why:** Backend accepts `X-Internal-Secret` header but no test verifies enforcement.

**File:** `tests/integration/clarity/test_internal_api_security.py`

**Test requirements (production mode - secret configured):**
- Missing `X-Internal-Secret` header → 403
- Wrong secret value → 403
- Correct secret → 201

**Test requirements (dev mode - empty secret):**
- No header required → 201

### 3. E2E OAuth Test with Real JWKS

**Why:** All auth tests mock `validate_jwt`. No test verifies actual JWKS fetch works.

**File:** `tests/integration/clarity/test_oauth_e2e.py`

**Approach:** Use test keys (simpler, runs in CI without infrastructure).

**Test requirements:**
- Token signed with test keys → validates successfully
- Wrong `iss` claim → rejected
- Wrong `aud` claim → rejected
- Expired token → rejected
- Missing `clarity.write` scope → rejected at enforcement

**Prerequisites:**
- Access to `sign_jwt` from backend crypto module (or equivalent test fixture)
- Test must clear JWKS cache to force real fetch

### 4. Deployment Documentation

**File:** `mcp_server/clarity/DEPLOYMENT.md`

**Required sections:**

**Environment Variables (Render):**
| Variable | Description |
|----------|-------------|
| `CLARITY_MCP_SERVER_URL` | Public URL of Clarity MCP server |
| `CLARITY_BACKEND_URL` | Backend API URL |
| `CLARITY_OAUTH_ISSUER_URL` | OAuth authorization server URL |
| `CLARITY_JWKS_URL` | JWKS endpoint URL |
| `CLARITY_ISSUER` | Expected JWT issuer claim |
| `CLARITY_AUDIENCE` | Expected JWT audience claim |
| `INTERNAL_API_SECRET` | Shared secret for MCP → Backend calls |
| `ENV` | `production` |

**How Users Connect (Manual):**
1. User opens ChatGPT Settings → Connectors
2. User adds custom MCP server URL
3. ChatGPT fetches `/.well-known/oauth-protected-resource`
4. OAuth flow redirects to Priority Guardian
5. User authenticates, ChatGPT receives token
6. ChatGPT calls Clarity tools with token

**Verification Checklist:**
- Discovery endpoint returns correct OAuth URLs
- Internal secret enforced (direct backend call without secret → 403)

**Not Required (no marketplace yet):**
- `CHATGPT_CLIENT_ID_CLARITY` - no connector registration exists
- `azp` validation - bypass is expected

## Success Criteria

1. ✅ Handler-level unknown tool tests pass (3 tests)
2. ✅ Internal secret enforcement tests pass (4 tests)
3. ✅ E2E OAuth tests pass with real JWKS fetch (5 tests)
4. ✅ `DEPLOYMENT.md` created
5. ✅ All existing tests still pass

## Files to Create

```
CREATE:
  tests/integration/clarity/test_tool_dispatcher.py
  tests/integration/clarity/test_internal_api_security.py
  tests/integration/clarity/test_oauth_e2e.py
  mcp_server/clarity/DEPLOYMENT.md
```

## Out of Scope

- ChatGPT connector registration (doesn't exist yet)
- `azp` validation (no client_id to validate)
- CORS restriction (endpoints require valid JWT anyway)
- Rate limiting (add if abuse observed)
