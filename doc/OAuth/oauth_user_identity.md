# OAuth User Identity Resolution — Analysis & Known Issues

**Last updated:** 2026-03-14  
**Status:** Investigation closed — Android connector failure confirmed as ChatGPT Android client bug. See `android_oauth_token_exchange_bug.md`.  
**Related files:** `backend/core/oauth_provider/authorize.py`, `session_service.py`, `cookies.py`

---

## How user identity is currently resolved

Every OAuth authorization request must be associated with an internal `CoreUser` record. The backend resolves identity via a three-step priority chain, implemented in `_resolve_user_identity()` in `authorize.py`.

### Priority 1 — `login_hint` parameter

If ChatGPT includes a `login_hint` query parameter on the `/oauth/pg/authorize` request, it contains the ChatGPT user's stable identifier. The backend looks up `CoreUser` by `chatgpt_user_id`. If found, that user is returned. If not found, a new `CoreUser` is created with `chatgpt_user_id` set.

This is the **ideal and stable path**. It produces a permanent, deterministic mapping: one ChatGPT user → one `CoreUser` record → one set of priorities and data.

**Current reality: ChatGPT does not send `login_hint`.**  
This has been known since early development. The `has_login_hint: false` field in every `oauth.authorize.request` log confirms it. The `login_hint` path is implemented and correct but effectively dead in production.

### Priority 2 — Browser session cookie (`pg_session`)

When `login_hint` is absent, the backend checks for a `pg_session` cookie set during a previous consent flow. The cookie contains a session token that maps to a `CoreUser` via the `oauth_sessions` table.

Cookie attributes:
- `HttpOnly`: true
- `Secure`: true in production
- `SameSite`: Lax
- `Path`: /oauth
- `Max-Age`: 2 years (sliding window)

If a valid, unexpired session cookie is present and maps to an existing user, that user is returned. The session TTL is extended on each successful lookup (sliding window).

Session token security:
- Tokens are hashed (SHA-256) before storage — plaintext tokens are never stored in the database
- Lookup is by hash, not by plaintext token
- Tokens are also Fernet-encrypted for audit/recovery purposes

This path works **only within the same browser context** — the cookie must have been set during a previous consent on the same device and browser. The cookie is set on the `302` redirect response at the end of consent.

### Priority 3 — New anonymous user

If neither `login_hint` nor a valid session cookie is available, a new `CoreUser` is created with `chatgpt_user_id = NULL`. This user has no stable identifier and cannot be reconnected to a previous user if they re-authorize.

---

## What the logs show on Android

Every Android OAuth attempt shows `has_login_hint: false` and resolves via `identity_source: session_cookie` after the first consent (once the cookie is set). The cookie-based path does stabilize onto one user across repeated attempts — `76092524` appears consistently via session cookie across multiple authorize requests.

However, **all Android attempts fail at the same point**: after `oauth.consent.allowed` and `oauth.consent.recorded`, there is no subsequent `oauth.token.request`. The auth code is issued and the redirect to `chatgpt.com/connector/oauth/...?code=...` fires — but ChatGPT on Android never exchanges the code for a token.

This means:
- The identity resolution chain itself is not causing the Android failure
- The correct user is found via session cookie
- The failure is in ChatGPT's Android app not completing the token exchange after the redirect

---

## The structural problem: no `login_hint`

While not the immediate cause of the Android connector failure, the absence of `login_hint` creates a fragile system with compounding risks:

### 1. New users created on every new browser/device

Each time a user connects from a new browser, clears cookies, uses a private/incognito window, or switches devices, Priority 3 fires and a new anonymous `CoreUser` is created. That new user starts with zero priorities and zero data — even if the same person connected before from a different context.

**Observed in logs:** User `0211c84b` (10:34) and user `76092524` (11:21) appear to be different users but may be the same person connecting from different contexts.

### 2. Session cookie is unreliable across Android/iOS

The `pg_session` cookie is set on the `302` redirect response from consent back to ChatGPT. On desktop browsers this works because the browser follows the redirect and stores the cookie. On Android, ChatGPT uses a Custom Chrome Tab. Whether the cookie set on the redirect response is persisted by the Custom Chrome Tab and sent back on subsequent `/oauth/pg/authorize` requests depends on Chrome's cookie handling for that tab context — which may not behave identically to a standard browser session.

If the Custom Chrome Tab does not persist the cookie across sessions or shares it with the host app rather than a browser session, the session cookie mechanism breaks silently and Priority 3 fires on every reconnect.

### 3. Multiple `CoreUser` records per real user accumulate over time

Every failed or abandoned OAuth attempt that reaches Priority 3 creates an orphan `CoreUser` row with no tokens, no priorities, and no way to be claimed. The GDPR retention task will eventually clean these up (6-month inactive account deletion) but they accumulate in the meantime and add noise to user counts.

---

## Root cause of Android connector failure (CLOSED)

Confirmed as a ChatGPT Android client bug. Full evidence chain and all backend invariants documented in `android_oauth_token_exchange_bug.md`.

Summary: the backend sends a correct `302` redirect with valid code, `state_present: true`, identical structure to Desktop and iPhone. Android receives it and does not call `/oauth/token`. Desktop and iPhone complete the token exchange in 1-2 seconds from the same backend.

---

## Recommended next steps (post-submission)

### Identity fragmentation
The `login_hint` problem is structural and will not be fixed by OpenAI sending it — they have not done so and there is no indication they will. The session cookie mechanism is the only available identity continuity mechanism and it is brittle on mobile. Options to consider post-submission:

- Accept the fragmentation as a known limitation of the ChatGPT MCP OAuth model
- Defer `CoreUser` creation to after consent (not at authorize time) to eliminate anonymous user DB pollution from aborted flows
- Track `chatgpt_user_id` via a different signal if OpenAI ever exposes it in JWT claims

---

## Summary table

| Scenario | Identity source | Stability | Risk |
|---|---|---|---|
| Desktop, first connect | new_anonymous | Session cookie for future reconnects | High — new user per browser clear |
| Desktop, reconnect same browser | session_cookie | Stable within same browser | Medium — breaks on cookie clear |
| iOS, first connect | new_anonymous | Session cookie in Safari | Medium — iOS cookie persistence varies |
| Android, first connect | new_anonymous | Session cookie in Custom Chrome Tab | High — Chrome Tab cookie persistence unreliable |
| Any platform with login_hint | login_hint | Permanent and stable | None — not currently sent by ChatGPT |
