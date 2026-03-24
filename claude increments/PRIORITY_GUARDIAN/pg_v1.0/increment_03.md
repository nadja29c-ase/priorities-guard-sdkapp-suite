# PG Disconnect: Add Google Token Revocation

## Problem

PG's disconnect endpoint (`backend/apps/priority_guardian/routers/offboarding_router.py`) marks the Google connection as revoked in the database but **never calls Google's revoke endpoint**. The user's Google refresh token remains valid at Google after "disconnect." This violates Google OAuth compliance requirement #20.

## What must happen

When a user disconnects, before marking `revoked_at` in DB, the backend must:

1. Load the Google connection (already done)
2. Decrypt the refresh token
3. Call Google's revoke endpoint (`https://oauth2.googleapis.com/revoke`)
4. Then mark connection as revoked in DB (already done)

Google revocation is best-effort — if it fails (token already revoked, network error), disconnect should still proceed. Log the failure but don't block.

## Reference implementation

Focused already does this correctly:
- `backend/apps/focused/logic/offboarding.py` — imports and calls `revoke_google_token()` from `backend/core/google_oauth`
- Uses `decrypt_token()` from `backend/core/encryption` to get the plaintext refresh token
- Passes the shared `httpx.AsyncClient` to `revoke_google_token()`

## Key files

- **Fix:** `backend/apps/priority_guardian/routers/offboarding_router.py`
- **Reference:** `backend/apps/focused/logic/offboarding.py` (the pattern to follow)
- **Reuse:** `backend/core/google_oauth.revoke_google_token()` (already exists)
- **Reuse:** `backend/core/encryption.decrypt_token()` (already exists)

## Constraints

- PG's offboarding router currently doesn't have access to an `httpx.AsyncClient`. Focused gets it from `request.app.state.http_client`. Check how PG's router gets its request context and use the same pattern, or check how `google_connection_router.py` handles it.
- `revoke_google_token()` expects the **refresh token** (not access token) to invalidate both. If no refresh token exists, skip revocation.
- Never log the decrypted token.
- Revocation failure must not prevent disconnect from completing.
- If `decrypt_token()` fails (corrupted data), log warning with correlation ID, skip revocation, proceed with disconnect.
- Ensure the httpx client used for revocation has a reasonable timeout (3–5s). The revoke call must not block the disconnect path.

## Unit tests

- Test: disconnect calls `revoke_google_token` when connection has refresh token
- Test: disconnect succeeds even when `revoke_google_token` fails (best-effort)
- Test: disconnect skips revocation when no refresh token exists
- Test: disconnect skips revocation when no connection exists (existing behavior preserved)

## Integration tests

- Test: full disconnect flow with mocked Google revoke endpoint returning 200
- Test: full disconnect flow with mocked Google revoke endpoint returning 400 (already revoked) — still succeeds di