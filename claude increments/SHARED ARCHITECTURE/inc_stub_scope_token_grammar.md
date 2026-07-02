# Increment (STUB / backlog): OAuth scope-token grammar validation

**Status:** Tracked, not scheduled. Surfaced by Codex adversarial review during inc_consent_template_fallthrough_guard (v2). Pre-existing. Lowest severity of the three split-out findings.

**Severity:** Medium/low.

## Problem (verified at source)
Scopes are handled via `scope.split()` (whitespace normalization) but there is NO RFC 6749 scope-token grammar validation anywhere in the authorize/register/consent path. Consequences:
- Malformed registered scope values can pass prefix checks: e.g. `focused.` (trailing dot, empty sub-scope), control characters, or very long strings.
- A scope longer than `CoreConsent.scope` (`String(100)`) would fail INSERT **after** the authorization code has already been committed (ties into the atomicity finding — orphaned code).
- The `consent_ui.py` comment claims it handles list-form scopes, but `create_authorization_code` is called with `scope` BEFORE the `scopes_list = scope.split() if isinstance(scope, str) else scope` normalization, so a list-form scope in the Redis context would hit `scope.split()` on a list → 500 before recording. (Minor: today the context always stores a string, so not currently triggered — but it's a latent type-assumption.)

## Fix direction
- Add RFC 6749 scope-token validation (scope-token = 1*( %x21 / %x23-5B / %x5D-7E ), space-delimited) at the registration boundary (`register_client.py`) and/or authorize boundary, rejecting malformed tokens with `invalid_scope`.
- Enforce a max scope length consistent with `CoreConsent.scope` (`String(100)`) BEFORE code creation, so an over-length scope is rejected up front, never after a code is minted.
- Normalize the scope type once (string vs list) at a single boundary so downstream code never guesses.

## Tests to add
- Malformed scope tokens (`focused.`, control chars, over-length) → rejected with invalid_scope at the boundary, before any code/context side effect.
- Over-length scope → rejected up front, never reaches `CoreConsent` INSERT.

## Notes
- Partly entangled with the atomicity finding (over-length-after-commit). Sequencing: the GETDEL and code/consent-atomicity increments are higher value; this can follow.
- Shared-backend change → predeploy + both-platform live consent check.
- Do NOT bundle — separate increment.
