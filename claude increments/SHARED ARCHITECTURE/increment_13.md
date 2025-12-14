# Increment 13: OAuth Token Exchange Integration

## Context

Increments 7B and 12 implemented OAuth components independently:
- **12**: `/consent` stores authorization codes in Redis only
- **7B**: `/token` expects codes in `oauth_authorization_codes` PostgreSQL table

**Result:** ChatGPT cannot complete OAuth flow. App is non-functional.

---

## Objective

Enable complete OAuth 2.1 flow: ChatGPT authenticates users and obtains valid JWT tokens for MCP tool calls.

---

## Requirements

### 1. Authorization Code Storage Alignment

`/oauth/focused/consent` (allow path) must store codes in `oauth_authorization_codes` table with **all** schema fields:

| Field | Type | Notes |
|-------|------|-------|
| `code` | string | Cryptographically random, unique |
| `user_id` | UUID | FK to core_users |
| `client_id` | string | ChatGPT's registered client |
| `code_challenge` | string | PKCE challenge (SHA256) |
| `code_challenge_method` | string | Always 'S256' |
| `redirect_uri` | string | Must match on token exchange |
| `scope` | string | Granted permissions |
| `state` | string | CSRF protection token |
| `nonce` | string | OIDC replay protection (optional) |
| `expires_at` | timestamp | 10 minutes from creation |
| `used` | boolean | Single-use enforcement |

**Source of truth:** PostgreSQL is the single source of truth for authorization codes and tokens. Redis may only be used for:
- CSRF/state glue for the browser consent flow
- Rate limiting
- Ephemeral UI context

### 2. Token Exchange & Persistence

`/oauth/focused/token` must:

**On authorization_code grant:**
- Retrieve code from `oauth_authorization_codes`
- Validate PKCE: verify `code_verifier` against stored `code_challenge`
- Validate `redirect_uri` **exactly matches** stored value (no normalization; mismatch = `invalid_grant`)
- Mark code `used = true` (single-use)
- Generate JWT access token (RS256, 1hr TTL)
- Generate opaque refresh token (30-day TTL)
- **Insert row into `oauth_access_tokens`:**

| Field | Value |
|-------|-------|
| `token` | JWT string or JTI reference |
| `user_id` | From auth code |
| `client_id` | From auth code |
| `scope` | From auth code |
| `token_type` | 'Bearer' |
| `jti` | UUID for revocation tracking |
| `expires_at` | now() + 1 hour |
| `revoked` | false |
| `created_at` | now() |
| `refresh_token_enc` | AES-256 encrypted refresh token |
| `refresh_token_expires_at` | now() + 30 days |

**On refresh_token grant:**
- Validate refresh token exists and not expired/revoked
- **Rotate tokens** (single-use refresh tokens per spec):
  - Mark old token row: `revoked = true`, `revoked_at = now()`
  - Create new row with fresh access + refresh tokens
- Return new token pair

### 3. End-to-End Flow Validation

Complete sequence must work:
```
POST /oauth/focused/register → client_id
GET /oauth/focused/authorize → consent screen
POST /oauth/focused/consent (allow) → redirect with code
POST /oauth/focused/token (code) → {access_token, refresh_token}
POST /oauth/focused/token (refresh) → {new_access_token, new_refresh_token}
MCP tool call with Bearer token → 200 success
```

### 4. Cleanup Job Compatibility

Verify existing Celery cleanup jobs (from 7B/7C) correctly handle:
- Expired authorization codes (>10 min)
- Expired/revoked tokens

No new logic required; confirm no regressions.

---

## Scope Boundaries

**In scope:**
- Fix code storage (Redis → PostgreSQL)
- Token persistence in `oauth_access_tokens`
- Refresh token rotation
- Unit tests + integration tests
- Manual validation with MCP Inspector

**Out of scope:**
- New features
- UI changes
- Deployment
- Token introspection endpoint

---

## Test Strategy

### Unit Tests (isolated, mocked DB/Redis)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Valid PKCE verification | Returns true |
| 2 | Invalid code_verifier | Returns false |
| 3 | Code expiration check (>10 min) | Returns expired |
| 4 | Refresh token encryption/decryption | Round-trips correctly |
| 5 | JWT claims construction | Verify **specific values**: `iss` = configured issuer URL, `sub` = internal user_id, `aud` = client_id, `exp` = 1hr from now, `scope` = granted scopes, `jti` = unique UUID |
| 6 | Refresh token rotation marks old revoked | `revoked=true`, `revoked_at` set |

### Integration Tests (real test DB + Redis, HTTP calls)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Full OAuth flow → MCP tool call | 200 + valid response |
| 2 | Token exchange with invalid code_verifier | 400 `invalid_grant` |
| 3 | Token exchange with expired code | 400 `invalid_grant` |
| 4 | Token exchange with reused code | 400 `invalid_grant` |
| 5 | Token exchange with wrong client_id | 401 `invalid_client` |
| 6 | Token exchange with wrong redirect_uri | 400 `invalid_grant` |
| 7 | Refresh token exchange | 200 + new tokens |
| 8 | Refresh with revoked token | 400 `invalid_grant` |
| 9 | Refresh token rotation (old token invalidated) | Second refresh with old token fails |
| 10 | Unsupported grant_type | 400 `unsupported_grant_type` |
| 11 | Missing required parameters | 400 `invalid_request` |
| 12 | **JWKS signature verification** | Token verifies against `/oauth/focused/jwks` using RS256 |
| 13 | Rate limit on /token | 429 `rate_limited` |
| 14 | Cleanup job deletes expired auth codes | Codes >10 min removed |

### E2E Validation (manual, MCP Inspector)

- [ ] Complete OAuth flow with MCP Inspector
- [ ] Call `check_calendar` tool with issued token
- [ ] Verify token refresh works after simulating expiry

#### MCP Inspector Validation Steps

**Prerequisites:**
1. Start the backend server: `poetry run uvicorn backend.main:app --reload`
2. Ensure Redis is running: `redis-server`
3. Ensure PostgreSQL is running with test database

**Step 1: Register OAuth Client**
```bash
curl -X POST http://localhost:8000/oauth/focused/register \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "MCP Inspector",
    "redirect_uris": ["http://localhost:5173/callback"],
    "grant_types": ["authorization_code", "refresh_token"],
    "scope": "focused.read focused.write focused.notify"
  }'
```
Save the returned `client_id` and `client_secret`.

**Step 2: Start MCP Inspector**
```bash
npx @anthropic-ai/mcp-inspector
```

**Step 3: Configure OAuth in MCP Inspector**
1. Open http://localhost:5173
2. Go to Settings → OAuth Configuration
3. Set:
   - Authorization URL: `http://localhost:8000/oauth/focused/authorize`
   - Token URL: `http://localhost:8000/oauth/focused/token`
   - Client ID: (from Step 1)
   - Client Secret: (from Step 1)
   - Scopes: `focused.read focused.write focused.notify`
   - PKCE: Enabled (S256)

**Step 4: Initiate OAuth Flow**
1. Click "Authorize" in MCP Inspector
2. Should redirect to consent screen
3. Click "Allow" to grant permissions
4. MCP Inspector receives authorization code
5. Exchanges code for tokens automatically

**Step 5: Verify Token Exchange**
Check server logs for:
```
oauth.token.request grant_type=authorization_code
oauth.token.success token_type=Bearer
```

**Step 6: Test MCP Tool Call**
1. In MCP Inspector, connect to the Priority Guardian MCP server
2. Call a tool (e.g., `check_calendar`)
3. Verify successful response (200 OK)

**Step 7: Test Token Refresh**
1. Wait for access token to expire (1 hour) or manually invalidate
2. Make another tool call
3. MCP Inspector should automatically refresh the token
4. Verify new tokens are issued

**Troubleshooting:**
- `invalid_grant`: Check PKCE verifier, redirect_uri exact match
- `invalid_client`: Verify client_id exists in database
- `401 Unauthorized` on tool call: Check JWT signature with JWKS endpoint
- Token not found: Ensure `refresh_token_hash` is set in database

---

## Files Likely Affected

**Verify actual paths before implementation:**
- Consent handler (POST `/oauth/focused/consent`)
- Token endpoint (POST `/oauth/focused/token`)
- Token service/logic module
- Database models for `oauth_authorization_codes`, `oauth_access_tokens`
- Test files

---

## Success Criteria

- [ ] Auth codes stored in PostgreSQL with full schema
- [ ] Tokens persisted in `oauth_access_tokens` (encrypted)
- [ ] PKCE validation passes end-to-end
- [ ] Refresh token rotation implemented (single-use)
- [ ] JWT signature validates against JWKS endpoint
- [ ] JWT claims contain correct values (not just present)
- [ ] MCP tool call succeeds with issued token
- [ ] All 6 unit tests pass
- [ ] All 14 integration tests pass
- [ ] Cleanup jobs compatible (no regressions)
- [ ] No regressions in existing OAuth tests (7B, 12)

---

## Security Requirements (from architecture)

| Requirement | Implementation |
|-------------|----------------|
| Tokens encrypted at rest | AES-256 for `refresh_token_enc` |
| Tokens never logged | Scrubbing already in place (7C) |
| Single-use auth codes | `used` flag enforcement |
| Single-use refresh tokens | Rotation with revocation |
| RS256 signing | Existing JWKS infrastructure |
| Rate limiting | Existing Redis counters (7C) |
| Redirect URI validation | Exact match, no normalization |

---

## Known Constraints

- No `/oauth/introspect` endpoint — revoked tokens valid until JWT expiry (1hr max)
- Single RSA key — no rotation mechanism yet
- MCP server validates stateless (JWKS only) — no DB lookup per request