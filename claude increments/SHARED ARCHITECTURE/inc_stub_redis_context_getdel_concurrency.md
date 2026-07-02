# Increment (STUB / backlog): Redis auth-context atomic consumption (one context → one code)

**Status:** Tracked, not scheduled. Surfaced by Codex adversarial review during inc_consent_template_fallthrough_guard (v2). Pre-existing. **Highest-value of the three split-out findings — schedule its own increment soon.**

**Severity:** Medium, but it is a genuine double-mint vector (not merely an audit invariant).

## Problem (verified at source)
`backend/core/oauth_provider/services/authorization_service.py::get_authorization_context` performs a Redis **GET then DELETE** (read, then separate delete), NOT an atomic `GETDEL`. The authorization context is intended to be single-use (deleted after read).

Race: two concurrent `/oauth/*/consent` POSTs with the same `auth_context_id` can BOTH read the context before either delete lands → both proceed → **two distinct authorization codes minted from one consent action.**

PKCE/token-replay protection does NOT cover this: replay protection prevents exchanging the SAME code twice, but here there are TWO different valid codes, each exchangeable once. So the user's single consent yields two usable codes.

## Fix direction
- Use Redis atomic `GETDEL` (single round-trip read-and-delete) so exactly one caller receives the context and all others get nothing.
- Confirm the Redis client/version in use supports `GETDEL` (Redis 6.2+). If not, use a Lua script or `MULTI/EXEC` with `WATCH`, or a `DEL`-returns-count guard (only the caller whose DEL returns 1 proceeds).
- Verify all call sites of `get_authorization_context` (authorize creates, consent consumes) tolerate the atomic semantics — the consume path must treat "context already taken" as the existing "expired or invalid" 400.

## Tests to add
- Concurrency test: two simultaneous consume calls for one context → exactly one succeeds (one code), the other gets the 400 invalid/expired path. Assert exactly one authorization code exists.
- Single-use unchanged: one consume succeeds, a second sequential consume of the same id fails.

## Notes
- Concurrency tests are harder; may need real Redis (not fakeredis) or a fake that models GETDEL atomicity faithfully — verify the test harness's Redis double actually models the atomicity, or the test proves nothing.
- Shared-backend change → predeploy + both-platform live consent check.
- Do NOT bundle with atomicity-of-code-and-consent or scope-grammar — separate increments.
