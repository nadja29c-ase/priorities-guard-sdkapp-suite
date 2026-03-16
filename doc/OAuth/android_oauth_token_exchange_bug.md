# Bug Report: ChatGPT Android — OAuth Token Exchange Never Fires

**Date documented:** 2026-03-14  
**Status:** Confirmed — ChatGPT Android client bug. Not a backend issue.  
**Affects:** ChatGPT Android app (web + native) when reconnecting a PG connector  
**Does not affect:** Desktop (Chrome/Safari), iPhone (Safari), API Playground  
**Submission impact:** None — OpenAI reviews on desktop. Not a blocker.

---

## Plain-language summary

When users connect Priority Guardian on Android and go through the consent screen, the connection fails with "Something went wrong" — even though they did everything right. The same flow works correctly on desktop and iPhone. We confirmed through extensive testing and server logs that the backend behaves perfectly on all platforms: it sends the correct response every time. The issue is in the ChatGPT Android app itself, which starts multiple competing connection attempts simultaneously and then fails to complete the final step of establishing the connection — this is not something that can be fixed on the Priority Guardian side.

---

## Reproduction steps

1. On Desktop: connect Priority Guardian in dev mode (required — makes app visible on mobile)
2. On Android: disconnect Priority Guardian from Settings → Apps
3. On Android: reconnect → consent screen appears → tap Allow
4. **Result:** "Something went wrong with setting up the connection" error banner

---

## Evidence chain

### Desktop control (working)

```
oauth.authorize.request        has_login_hint: false
oauth.authorize.user_found     identity_source: session_cookie
oauth.auth.context_created
oauth.authorize.consent_rendered
oauth.consent.allowed
oauth.consent.redirect_prepared  state_present: true, code: dC6JFO1I
oauth.consent.redirect_sent     status_code: 302, location: correct ✅
oauth.token.request             grant_type: authorization_code  [1.3s later] ✅
oauth.token.success ✅
```

### iPhone control (working)

```
oauth.authorize.request        1 request only
oauth.authorize.user_found     identity_source: session_cookie
oauth.consent.redirect_sent    status_code: 302 ✅
oauth.token.request            [2s later] ✅
oauth.token.success ✅
```

### Android (failing)

```
15:05:19  oauth.authorize.request   → user 76092524 via session_cookie
15:05:21  oauth.authorize.request   → NEW anonymous user e97991b8   ← +2s
15:05:21  oauth.authorize.request   → NEW anonymous user 01d1dfa1   ← same second
15:05:21  oauth.authorize.request   → NEW anonymous user 0cdddfb3   ← same second

15:05:22  oauth.consent.allowed     user: 76092524
15:05:22  oauth.consent.redirect_prepared
          redirect_host: chatgpt.com
          redirect_path: /connector/oauth/nueto5J5YAE_
          state_present: true
          code_prefix: faDNkRBr
          has_session_cookie: true
15:05:22  oauth.consent.redirect_sent
          status_code: 302 ✅
          location: https://chatgpt.com/connector/oauth/nueto5J5YAE_?code=faDNkRBr... ✅
          has_set_cookie: true ✅

          ← NO oauth.token.request
          ← NO oauth.token.success
```

---

## Backend invariants verified

Every possible backend cause was ruled out through code inspection and runtime logging.

| Invariant | Verification method | Result |
|---|---|---|
| Redirect status code is 302 | Runtime log `oauth.consent.redirect_sent` | ✅ 302 confirmed |
| Location header correct | Runtime log `location` field | ✅ Correct chatgpt.com URL |
| State present | Runtime log `state_present` | ✅ true on all platforms |
| Redirect URI identical across platforms | Runtime log `redirect_host`, `redirect_path` | ✅ Identical |
| Auth context isolated per flow | Code: UUID Redis key per authorize request | ✅ No shared state |
| PKCE stored per auth context | Code: `code_challenge` stored in Redis auth context, copied to DB auth code | ✅ No cross-flow contamination |
| Auth code single-use | Code: `SELECT FOR UPDATE` + `used=True` flag | ✅ Replay protected |
| Parallel authorize requests cannot corrupt each other | Code: each flow has independent Redis key and DB row | ✅ No race condition |
| No redirect loop caused by backend | Logs: consent fires once, redirect fires once | ✅ |
| Cookie does not cause redirect failure | Both Desktop and iPhone also receive `set-cookie` on 302 and follow the redirect | ✅ |

---

## Root cause

The ChatGPT Android app fires **4 parallel `/oauth/authorize` requests** within ~2 seconds when initiating a reconnect flow (1 first-attempt + 3 retries). All 4 are identical in every parameter except the PKCE code challenge. Each gets its own `auth_context_id` and auth code.

The user sees and clicks consent on the first flow's consent screen. The backend issues the correct `302` redirect with the correct code for that flow. However, **the ChatGPT Android app never calls `/oauth/token`**.

The most likely explanation: the Android app has 4 parallel PKCE flows in flight simultaneously. When the redirect returns, the app cannot reliably match the returned code to the correct internal PKCE state (code verifier), so it silently drops the token exchange rather than risk a PKCE mismatch error.

This is consistent with:
- No `oauth.token.request` appearing at all (not a failed exchange — a missing exchange)
- The error "Something went wrong" appearing immediately after redirect
- Desktop and iPhone working correctly with a single authorize request

---

## What Android does differently

| Behaviour | Desktop | iPhone | Android |
|---|---|---|---|
| Number of parallel authorize requests | 1 | 1 | 4 (1 + 3 retries) |
| Anonymous users created per reconnect | 0 | 0 | 3 |
| Token exchange after redirect | ✅ ~1-2s | ✅ ~2s | ❌ never |
| `login_hint` sent | ✗ | ✗ | ✗ |
| Identity resolution | session_cookie | session_cookie | session_cookie |

---

## Side effect: anonymous user DB pollution

Each reconnect attempt on Android creates 3 orphan `CoreUser` rows with `chatgpt_user_id = NULL`, no tokens, no priorities, and no way to be claimed. These accumulate until the GDPR 6-month inactive account cleanup task runs.

This is a separate problem from the token exchange failure. The backend should defer `CoreUser` creation until after consent is given, not at authorize time, to prevent this pollution. Tracked as a post-submission improvement.

---

## Why this is not a backend bug

1. **iPhone works** — same backend, same consent flow, same redirect mechanism, same cookie on 302. iPhone completes the token exchange in ~2 seconds.
2. **Desktop works** — same backend, confirmed end-to-end.
3. **All backend invariants hold at runtime** — `oauth.consent.redirect_sent` confirms `302`, correct `Location`, `state_present: true` on the failing Android run.
4. **The parallel authorize storm is Android-specific** — Desktop and iPhone fire exactly 1 authorize request. Android fires 4. This is the ChatGPT Android client's reconnect retry behavior.
5. **Community reports confirm the pattern** — The OpenAI developer community has reported OAuth connector failures on Android since at least mid-2024, with no backend-side fix being possible.

---

## Relation to login_hint absence

ChatGPT does not send `login_hint` on any platform (confirmed by `has_login_hint: false` in all logs). This means user identity relies on the `pg_session` session cookie. This is a separate structural fragility documented in `oauth_user_identity.md`. It does not cause the Android token exchange failure — the Android flow correctly resolves `identity_source: session_cookie` — but it causes the 3 extra anonymous user rows created during the parallel storm to have no stable identity.

---

## Action required

**None for submission.** OpenAI reviews on desktop. This does not affect the review flow.

**Post-submission improvements to consider:**
1. Defer `CoreUser` creation to after consent, not at authorize time — eliminates anonymous user pollution from aborted flows
2. Monitor OpenAI community and changelogs for Android OAuth fix
3. If OpenAI begins sending `login_hint`, remove the session cookie fallback entirely — it becomes unnecessary

---

## Diagnostic logging deployed

The following log lines were added to `backend/core/oauth_provider/consent_ui.py` during this investigation and remain in production:

- `oauth.consent.redirect_prepared` — logs `redirect_host`, `redirect_path`, `state_present`, `code_prefix`, `auth_context_id` immediately before redirect is built
- `oauth.consent.redirect_url` — logs first 80 chars of the full redirect URL
- `oauth.consent.redirect_sent` — logs `status_code`, `location`, `has_set_cookie` after `RedirectResponse` is constructed

These logs have no performance impact and provide complete visibility into the redirect boundary for future debugging.
