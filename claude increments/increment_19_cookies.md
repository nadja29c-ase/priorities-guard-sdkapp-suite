# Increment 19: Cross-App User Identification via OAuth Sessions

## Problem

ChatGPT does not provide `login_hint`. Every OAuth authorization creates a new anonymous `CoreUser`. Same human authorizing Focused then Decliner = two separate identities, no linkage.

## Solution

Browser session cookie during OAuth consent flow. When user returns to authorize a second app, recognize them via cookie and reuse existing `CoreUser`.

---

## Current State

| Component | Status |
|-----------|--------|
| `CoreUser` model | ✅ Exists |
| `_get_or_create_user()` in authorize.py | ✅ Creates user in `/authorize` |
| `CoreConsent` model | ✅ Exists |
| `/oauth/focused/authorize` | ✅ Works |
| `/oauth/focused/consent` | ✅ Works |
| Session management | ❌ Missing |
| Cross-app user linking | ❌ Missing |

---

## Identity Resolution Chain (Future-Proof)

Priority order in `/authorize`:

```
1. login_hint provided? → find_or_create_by_chatgpt_id(login_hint)
2. Valid session cookie? → get_user_from_session(token)
3. Neither? → create_anonymous_user()
```

This ensures forward compatibility if OpenAI ever adds `login_hint`.

---

## Implementation Overview

### 1. New Table: `oauth_sessions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID FK | References `core_users.id` ON DELETE CASCADE |
| `session_token` | VARCHAR(64) | Random token stored in cookie, UNIQUE, indexed |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `expires_at` | TIMESTAMPTZ | 30 days from last use |

**No `last_seen_at` column.** Expiry is extended on read by updating `expires_at`.

### 2. Session Service Functions

**Location:** `backend/core/oauth_provider/services/session_service.py`

| Function | Purpose |
|----------|---------|
| `create_session(user_id, db) -> str` | Create session, return token |
| `get_session_user(token, db) -> UUID or None` | Look up user, extend expiry, return user_id |
| `delete_session(token, db)` | Delete session row |
| `cleanup_expired_sessions(db)` | Delete all expired rows (Celery task) |

`get_session_user()` extends `expires_at` by 30 days on every successful read (sliding window).

### 3. Cookie Configuration

| Setting | Value |
|---------|-------|
| Name | `pg_session` |
| Max-Age | 30 days |
| HttpOnly | true |
| Secure | true |
| SameSite | Lax |
| Path | `/oauth` |

### 4. Modified `/authorize` Flow

**File:** `backend/core/oauth_provider/authorize.py`

Current `_get_or_create_user()` must be replaced with identity resolution chain:

```
Read pg_session cookie from request
    │
    ├── login_hint provided?
    │   └── Yes → find or create user by chatgpt_user_id
    │
    ├── Valid session cookie?
    │   └── Yes → get user_id from session, extend session expiry
    │
    └── Neither?
        └── Create new anonymous CoreUser
```

The resolved `user_id` is written into `auth_context` stored in Redis.

### 5. Modified `/consent` Flow

**File:** `backend/core/oauth_provider/consent_ui.py`

After user clicks "Allow" and authorization code is generated:

1. Check if session cookie already exists and is valid
2. If not, create new session for this user
3. Set `pg_session` cookie on redirect response

Cookie is set here because this is the moment user explicitly consents.

### 6. Disconnect Semantics

| Action | Cookie Behavior |
|--------|-----------------|
| Disconnect Google only (Increment 10) | **Keep cookie** — user remains identified |
| Revoke app OAuth (`/oauth/revoke`) | **Delete cookie** — user disconnects from suite |
| Delete all my data | **Delete cookie** — full account removal |

**Files to modify:**
- `backend/core/oauth_provider/revoke.py`
- `backend/apps/focused/routers/offboarding_router.py` (if full deletion added)

### 7. Session Cleanup

Weekly Celery task:

```sql
DELETE FROM oauth_sessions WHERE expires_at < NOW();
```

---

## Edge Cases (Explicit Decisions)

### Incognito / Private Browsing

- Session cookie not sent in incognito
- New anonymous `CoreUser` created
- **No automatic merging** with regular browser identity
- This is expected and acceptable

### Multiple Devices

- Each device/browser has its own session cookie
- Same human on phone vs laptop = two `CoreUser` records
- **No cross-device linking** (would require account system)
- Acceptable for MVP

### Cookie Expiration

- User doesn't visit for 30+ days → session expires
- Next authorization creates new `CoreUser`
- Old identity remains (for data retention compliance)
- **No automatic linking** to expired identity

---

## Constraint Verification ✅

Verified that existing constraints allow multi-app users:

| Table | Constraint | Multi-App Safe? |
|-------|-----------|-----------------|
| `oauth_access_tokens` | None on (user_id, client_id) | ✅ Yes |
| `oauth_authorization_codes` | None on (user_id, client_id) | ✅ Yes |
| `core_connections` | `uq_user_provider` | ✅ Only affects Google/Apple |

Same `CoreUser.id` can have tokens for Focused, Decliner, and future apps.

---

## Security Considerations

- **Cookie is HttpOnly**: Not accessible via JavaScript (XSS protection)
- **Cookie is Secure**: HTTPS only
- **Cookie is SameSite=Lax**: Sent on OAuth redirects, blocked on cross-site POST
- **Session token is random**: 32 bytes, cryptographically secure
- **Session stored server-side**: Cookie contains only opaque token
- **Scoped to /oauth path**: Not sent on API requests

---

## GDPR Compliance

This is a **strictly necessary functional cookie** for cross-app identity. No consent banner required.

**Privacy policy addition:**
> "We use a session cookie during authorization to recognize returning users across Priority Guardian apps. This cookie is not used for tracking or advertising and expires after 30 days of inactivity."

---

## File Changes Summary

| File | Action |
|------|--------|
| `backend/core/oauth_provider/models.py` | Add `OAuthSession` model |
| `backend/core/oauth_provider/services/session_service.py` | **New file** — session CRUD |
| `backend/core/oauth_provider/authorize.py` | Read cookie, identity resolution chain |
| `backend/core/oauth_provider/consent_ui.py` | Set cookie after consent |
| `backend/core/oauth_provider/revoke.py` | Delete cookie on revocation |
| `backend/alembic/versions/xxx_add_oauth_sessions.py` | Migration |

---

## Acceptance Criteria

1. New user authorizes Focused → session cookie set
2. Same browser authorizes second app → same `user_id` used
3. Different browser/device → new `user_id` (expected)
4. Incognito browser → new `user_id` (expected)
5. Cookie expires after 30 days of inactivity
6. Session expiry extended on each use (sliding window)
7. App revocation deletes session cookie
8. Expired sessions cleaned up by Celery task
9. All existing OAuth tests pass
10. Cookie not sent outside `/oauth` path
11. If `login_hint` provided (future), it takes priority over cookie

---

## Testing Approach

**Unit:**
- Session creation returns valid token
- Session lookup returns correct user_id
- Session lookup extends expiry
- Expired session returns None
- Session deletion works

**Integration:**
- `/authorize` with no cookie → new user created
- `/authorize` with valid cookie → existing user used
- `/authorize` with expired cookie → new user created
- `/consent` Allow → cookie set on response
- `/revoke` → cookie deleted
- `login_hint` takes priority over cookie (when provided)

**Manual E2E:**
- Authorize Focused in browser → note user_id in DB
- Authorize hypothetical second app in same browser → verify same user_id
- Verify cookie present in browser dev tools
- Clear cookies → authorize again → verify new user_id