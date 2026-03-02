# Increment 20: OAuth Security Hardening Bundle

## Context

Shared backend infrastructure. Three security hardening items bundled into one increment, all identified during the OAuth security audit (2026-03-01). None are blocking bugs — all are defense-in-depth improvements.

**Items:**
- **#3**: Session tokens stored in plaintext → hash before storage
- **#4**: No rate limit on consent POST endpoint → add IP-based rate limit
- **#6**: No state parameter length validation → add 512-char limit

---

## Item #3: Hash Session Tokens Before Storage

### Problem

`oauth_sessions.session_token` stores the plaintext token. A database breach exposes all active session tokens, allowing session hijacking. Refresh tokens already follow the hash-before-store pattern (`OAuthAccessToken.refresh_token_hash`).

### What to Change

Follow the exact same pattern as refresh tokens in `token_service.py`:
- Store a SHA-256 hash of the session token for lookup
- Store the token encrypted (Fernet) for recovery/audit if needed
- Look up sessions by hash (indexed), never by plaintext

**File: `backend/core/oauth_provider/models.py` — OAuthSession model**

Add two new columns:
- `session_token_hash: Mapped[str] = mapped_column(String(64), nullable=True, unique=True, index=True)` — SHA-256 hash for O(1) lookup
- `session_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)` — Fernet-encrypted token for audit

Keep `session_token` column temporarily for the migration (see migration notes below).

**File: `backend/core/encryption.py`**

Add a generic `hash_token(token: str) -> str` function, or reuse `hash_refresh_token`. The logic is identical (SHA-256 hex digest). If reusing, consider renaming to `hash_token` for clarity since it's now used for both refresh tokens and session tokens. Either approach is fine — decide and be consistent.

**File: `backend/core/oauth_provider/services/session_service.py`**

- `create_session`: Hash and encrypt the token before storing. Store `session_token_hash` and `session_token_enc`. Continue storing plaintext in `session_token` temporarily (migration path). Return the plaintext token to the caller (for the cookie).
- `get_session_user`: Look up by `session_token_hash` instead of `session_token`. Hash the incoming token, query by hash.
- `delete_session`: Look up by `session_token_hash` instead of `session_token`. Hash the incoming token, query by hash.

**File: `backend/alembic/versions/` — New migration**

Two-phase migration approach:
1. **This increment (Phase 1)**: Three-step migration (all in one migration file, but ordered carefully):
   - **Step 1**: Add `session_token_hash` (String(64), nullable, NO unique constraint yet) and `session_token_enc` (Text, nullable) columns.
   - **Step 2**: Backfill existing rows in batches. For each row: compute `hashlib.sha256(session_token.encode()).hexdigest()` → write to `session_token_hash`. For encryption: only populate `session_token_enc` if the Fernet key is available in the migration environment. If not, leave NULL — app code will lazily populate on next session access.
   - **Step 3**: After backfill completes, create the unique index on `session_token_hash` explicitly via `op.create_index()`. Do NOT rely on SQLAlchemy model metadata to create the index implicitly.
   
   **Critical**: Do NOT combine column creation + unique constraint in the same step. If backfill fails partway, you'd have NULL rows violating uniqueness.

2. **Future increment (Phase 2)**: Once all sessions have been rotated or expired naturally (after SESSION_LIFETIME_DAYS), drop the `session_token` column and make `session_token_hash` NOT NULL.

**Migration must NOT import application code** (`hash_refresh_token`, `encrypt_token`, etc.). Use `hashlib.sha256` directly in the migration. Application code can change after the migration is written — migrations must be self-contained and stable across time. For encryption, use inline Fernet with `os.environ.get("ENCRYPTION_KEY")` if available, or skip encryption and let app code backfill lazily.

### What NOT to Change

- Cookie handling (`cookies.py`) — cookie still stores/sends the plaintext token (it must, that's how cookies work)
- The `session_token` column — keep it for now (Phase 1), drop in Phase 2
- `delete_user_sessions` — already queries by `user_id`, not by token
- `cleanup_expired_sessions` — already queries by `expires_at`, not by token

---

## Item #4: Rate Limit Consent POST Endpoint

### Problem

The consent POST endpoint (`/oauth/focused/consent`, `/oauth/pg/consent`) has no rate limiting. While the auth_context is single-use with 10-minute TTL (limiting practical abuse), adding rate limiting is consistent with all other OAuth endpoints and provides defense-in-depth.

### What to Change

**File: `backend/core/oauth_provider/consent_ui.py`**

Add IP-based rate limiting at the top of `consent_endpoint`, before parsing form data. Follow the exact same pattern as `authorize_endpoint` in `authorize.py`.

```python
# Rate limit by IP
ip = get_client_ip(request)
await check_rate_limit(
    key=f"ratelimit:oauth:consent:ip:{ip}",
    limit=20,
    window=60,
    request=request
)
```

Rate: 20 requests/minute per IP. This is more restrictive than `/authorize` (100/min) because consent is a lower-frequency action — a legitimate user clicks "Allow" once per app authorization.

Add imports: `from backend.core.rate_limit import check_rate_limit, get_client_ip`

### What NOT to Change

- No new rate limit helper function needed — reuse existing `check_rate_limit`
- No changes to the rate_limit module itself

---

## Item #6: State Parameter Length Validation

### Problem

The `state` parameter in `/authorize` is accepted with no maximum length. An attacker could send a megabyte-long state → stored in Redis (10-minute TTL) → appended to redirect URL. The DB column is already `String(512)` but the Redis path and redirect URL have no limit.

### What to Change

**File: `backend/core/oauth_provider/authorize.py`**

Add state length validation after client+redirect_uri validation (so we can use `_error_redirect`), before `response_type` validation. Place it right after the PKCE validation block:

```python
# Validate state length (prevent Redis/redirect URL abuse)
if state and len(state) > 512:
    return _error_redirect(
        redirect_uri, None, "invalid_request", "state parameter too long"
    )
```

Note: pass `None` as state to `_error_redirect`, not the oversized state itself — we don't want to echo a megabyte-long value back in the redirect URL.

### What NOT to Change

- The `OAuthAuthorizationCode.state` column — already `String(512)`
- The OAuthState model — different table (CSRF states, not OAuth state param)
- Redis storage — no changes needed (the validation prevents oversized values from reaching Redis)

---

## Unit Tests

**File: `tests/unit/core/test_session_service.py`** (new or existing — check if it exists)

### Session token hashing tests:

1. **test_create_session_stores_hash_and_encrypted** — Create a session. Assert `session_token_hash` is a 64-char hex string. Assert `session_token_enc` is a non-empty string. Assert both are present on the DB row.

2. **test_get_session_user_by_hash** — Create a session, get the plaintext token. Call `get_session_user(token)`. Assert it returns the correct user_id. Assert the lookup uses `session_token_hash` (not `session_token`).

3. **test_delete_session_by_hash** — Create a session. Call `delete_session(token)`. Assert the session is deleted. Assert lookup was by hash.

4. **test_session_token_hash_is_deterministic** — Hash the same token twice. Assert both hashes are identical.

**File: `tests/unit/core/test_consent_ui.py`** (existing)

### Rate limit test:

5. **test_consent_rate_limited_by_ip** — Mock `check_rate_limit` to raise `RateLimitExceeded`. POST to `/oauth/pg/consent`. Assert 429 response.

**File: `tests/unit/core/test_authorize.py`** (existing — check actual filename)

### State length tests:

6. **test_state_over_512_chars_returns_error** — GET `/oauth/pg/authorize` with valid params and `state="x" * 513`. Assert redirect with `error=invalid_request` and `error_description` containing "state parameter too long". Assert the oversized state is NOT echoed in the redirect URL.

7. **test_state_exactly_512_chars_accepted** — GET `/oauth/pg/authorize` with valid params and `state="x" * 512`. Assert consent screen renders (no error).

8. **test_state_none_accepted** — GET `/oauth/pg/authorize` with valid params and no state. Assert consent screen renders.

---

## Integration Tests

### Migration test:

9. **test_migration_backfills_session_token_hash** — Before migration: insert a row into `oauth_sessions` with only `session_token`. Run migration. Assert `session_token_hash` equals `hashlib.sha256(session_token.encode()).hexdigest()`. Assert `session_token_enc` is either populated (if Fernet key available in test env) or NULL (acceptable — app code backfills lazily). If test environment has the encryption key, also assert the encrypted value decrypts to the original token.

---

## Acceptance Criteria

- [ ] `OAuthSession` model has `session_token_hash` (String(64), indexed, unique) and `session_token_enc` (Text) columns
- [ ] `create_session` stores hash and encrypted token alongside plaintext
- [ ] `get_session_user` queries by `session_token_hash`, not `session_token`
- [ ] `delete_session` queries by `session_token_hash`, not `session_token`
- [ ] Alembic migration: Step 1 adds nullable columns (no unique constraint), Step 2 backfills hashes, Step 3 creates unique index
- [ ] Migration uses `hashlib.sha256` directly — does NOT import application code
- [ ] Migration handles missing encryption key gracefully (skips `session_token_enc` backfill)
- [ ] `session_token` column retained (Phase 1 — drop in future Phase 2)
- [ ] Consent POST endpoints rate limited at 20/min per IP
- [ ] Rate limit uses same `check_rate_limit` + `get_client_ip` as other endpoints
- [ ] State parameter validated: `len > 512` → `_error_redirect` with `state=None`
- [ ] State validation placed after client+redirect_uri validation, before response_type
- [ ] Oversized state NOT echoed in error redirect
- [ ] All 9 tests pass (4 session hash + 1 rate limit + 3 state + 1 migration)
- [ ] All existing OAuth test suites pass (no regression)
- [ ] No sensitive data in new log statements

## Files to Modify

| File | Change |
|---|---|
| `backend/core/oauth_provider/models.py` | Add `session_token_hash` and `session_token_enc` columns to OAuthSession |
| `backend/core/oauth_provider/services/session_service.py` | Hash/encrypt on create, lookup by hash |
| `backend/core/encryption.py` | Optional: rename `hash_refresh_token` → `hash_token` or add alias |
| `backend/core/oauth_provider/consent_ui.py` | Add rate limit at top of `consent_endpoint` |
| `backend/core/oauth_provider/authorize.py` | Add state length validation after PKCE block |
| `backend/alembic/versions/` | New migration: add columns + backfill |
| `tests/unit/core/test_session_service.py` | 4 new session hash tests |
| `tests/unit/core/test_consent_ui.py` | 1 new rate limit test |
| `tests/unit/core/test_authorize.py` | 3 new state validation tests |

## Files NOT to Touch

- `backend/core/oauth_provider/cookies.py` — cookie handling unchanged
- `backend/core/rate_limit.py` — no new helpers needed
- `backend/core/oauth_provider/discovery.py` — no changes
- MCP server code — no changes
- `backend/core/oauth_provider/services/authorization_service.py` — Redis storage unchanged (state validated before it reaches Redis)

## Compliance Notes

- Session token hashing aligns with GDPR data protection by design (Art. 25): minimizing exposure of authentication material at rest
- No new data categories introduced
- No new external dependencies
- Data Retention Strategy unchanged (session cleanup already handled by Celery)

## Reference

- **Audit source:** OAuth security audit transcript (2026-03-01)
- **Existing pattern:** `hash_refresh_token` in `encryption.py`, used by `token_service.py`
- **Related:** ADR-002 (lock eviction — separate increment, already completed)
