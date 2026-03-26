# ADR-001: Anonymous User Identity Resolution and Board Isolation — MindSort AI

**Date:** 2026-03-25
**Status:** Active — partial mitigation applied, proper fix pending OpenAI CMID availability

---

## Context

MindSort AI uses the shared Priority Guard Suite OAuth provider. ChatGPT acts as the OAuth client and does **not** send `login_hint` (ChatGPT user ID) in production — confirmed across iOS and desktop clients as of March 2026.

Without `login_hint`, the identity resolution chain in `backend/core/oauth_provider/authorize.py` falls through to:

1. `login_hint` provided → find or create by `chatgpt_user_id` ← **never reached in production**
2. Valid session cookie → get existing `CoreUser` from session ← **primary path in production**
3. Neither → create new anonymous `CoreUser` ← **first-time connection path**

This means every MindSort AI user is effectively anonymous: their `CoreUser` row has `chatgpt_user_id = NULL` and their identity is maintained solely by a browser session cookie.

---

## Problem

### Shared-device board leakage

If two different ChatGPT users access MindSort AI on the same device in the same browser session without clearing cookies:

1. User A connects → session cookie set → `CoreUser` UUID-A created
2. User B connects on same device → no `login_hint` → session cookie found → `get_session_user()` returns UUID-A → User B is resolved to UUID-A
3. User B calls `load_saved_board` or `read_saved_board` → backend query: `WHERE user_id = UUID-A` → returns User A's board
4. **User B sees User A's saved board**

This is a real data leakage scenario. It requires physical device sharing and the same browser session, but it is not theoretical. Realistic triggers: shared family computers, workplace demos, shared devices.

### Why blocking anonymous users is not viable

The obvious mitigation — blocking board retrieval for users with `chatgpt_user_id = NULL` — would break the app for all iOS and desktop users, since every user is anonymous in production. This was explicitly evaluated and rejected.

---

## Decision

### Applied mitigation (2026-03-25)

Reduce `SESSION_LIFETIME_DAYS` from 730 (2 years) to 30 (30 days) in `backend/core/oauth_provider/services/session_service.py`.

**Effect:** The shared-device leakage window is reduced from 2 years to 30 days. After 30 days of inactivity, the session cookie expires and a new `CoreUser` is created on next connection, breaking the cross-user link.

**Limitation:** Does not eliminate the risk — it only shrinks the window. Two users on the same device within 30 days of each other can still experience the issue.

### Deferred proper fix

When OpenAI begins sending `login_hint` reliably (announced as CMID — Consistent Member ID), implement:

1. Store `chatgpt_user_id` on `CoreUser` at authorization time (currently `NULL` for all anonymous users)
2. On subsequent connections: look up existing `CoreUser` by `chatgpt_user_id` first, before falling back to session cookie
3. Session cookie becomes a secondary fallback within the same user's identity, not a cross-user binding mechanism

This eliminates anonymous identity ambiguity entirely and makes cross-user board leakage impossible.

---

## Data isolation audit result

Outside of the anonymous identity ambiguity described above, the board isolation chain is correct at every layer:

| Layer | Mechanism | Status |
|---|---|---|
| JWT validation | `user_id` from validated `sub` claim only — no client override possible | ✅ Correct |
| MCP → backend | `user_id` set as `X-User-ID` header by MCP server, not by tool arguments | ✅ Correct |
| Internal secret | `verify_internal_call` on all clarity router endpoints | ✅ Correct |
| Backend query | `WHERE user_id = ?` strict filter, no cross-user joins | ✅ Correct |
| DB constraint | `UniqueConstraint("user_id")` on `clarity_clusters` | ✅ Correct |
| UUID validation | `validate_user_id_header` rejects non-UUID values with 401 | ✅ Correct |

There is no path for remote exploitation or accidental cross-user access outside of the shared-device session cookie scenario documented here.

---

## Consequences

- **Session TTL = 30 days** — applies to new sessions and extended sessions going forward. Existing sessions in the DB keep their current `expires_at`. No migration needed.
- **Android orphan users** — the Android parallel PKCE flow bug (ChatGPT fires parallel flows and never calls `/oauth/token`) creates orphan anonymous `CoreUser` rows with no board data. These are harmless from an isolation perspective but accumulate in the DB. Cleanup is handled by the existing 6-month orphan user Celery task.
- **When CMID lands** — implement `chatgpt_user_id` storage and cross-device identity merge. At that point, `SESSION_LIFETIME_DAYS` can be revisited (shorter is safer, but cross-device continuity becomes possible via `chatgpt_user_id` instead).

---

## Files affected

| File | Change |
|---|---|
| `backend/core/oauth_provider/services/session_service.py` | `SESSION_LIFETIME_DAYS` reduced from 730 to 30 |
| `backend/core/oauth_provider/authorize.py` | Identity resolution chain — no change, documented here for reference |
| `backend/apps/clarity/routers/clusters_router.py` | Board retrieval — no change, isolation verified |
