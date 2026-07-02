# Increment (STUB / backlog): OAuth auth-code + consent-record atomicity

**Status:** Tracked, not scheduled. Surfaced by Codex adversarial review during inc_consent_template_fallthrough_guard (v2). Pre-existing (Increment 12/17 era), NOT introduced by that increment. Deliberately split out to keep the consent-classification increment focused.

**Severity:** Medium. Audit-invariant violation, not an easy external token-mint path (the response likely 500s before the code reaches the client).

## Problem (verified at source)
In the consent "allow" flow (`backend/core/oauth_provider/consent_ui.py::consent_endpoint`):
1. `create_authorization_code(...)` commits the authorization code to DB (`consent_service.py` — its own `await db.commit()`).
2. `record_consent(...)` commits the GDPR consent record LATER (separate `await db.commit()`).

If consent persistence fails AFTER code creation, a valid unused authorization code exists in the DB with NO corresponding consent record. This violates the audit invariant "every minted code/token has a recorded consent."

## Fix direction (decide at implementation)
- Option A: single transaction covering both code creation and consent recording (one commit; both or neither).
- Option B: record consent FIRST, then create the code (consent without a code is harmless; a code without consent is the defect).
- Option B is simpler and likely sufficient; A is stricter. Verify the two services can share one session/transaction without ordering issues (FK: consent → core_users; code → core_users; both need the user to exist first).

## Tests to add
- Failure injected between code creation and consent recording → assert no orphaned code remains (or, under B, no code exists if consent failed).
- Happy path unchanged: both records present after a successful allow.

## Notes
- Shared-backend change → predeploy + both-platform live consent check (per inc_06).
- DB-integrity standard: include integrity tests for the transactional behavior.
- Do NOT bundle with the GETDEL concurrency fix or scope-grammar fix — separate increments.
