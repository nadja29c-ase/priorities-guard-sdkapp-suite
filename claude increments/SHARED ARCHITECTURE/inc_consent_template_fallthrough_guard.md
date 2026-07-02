# Increment: Consent scope classification + fallthrough guard (rewritten v2)

**Type:** Backend hardening increment (shared OAuth provider). Touches the consent path serving ALL apps (Focused, Priority Guardian, MindSort) on BOTH platforms (ChatGPT + Claude). Blast radius is large despite a focused diff.

**v2 NOTE — REPLACES an existing v1 implementation that is CURRENTLY IN THE CODEBASE.** A first version of this increment is already implemented in `authorize.py` and `consent_ui.py` (the prefix-`any()` selector that runs AFTER auth-context creation). Adversarial review found it has a real scope bypass and an ordering defect. **This is the one case where "Copy and Adjust, Never Rewrite" does NOT apply: you are deliberately REPLACING the existing selector, not preserving it.** Do not treat the current `any()`-based selector as the baseline to copy. The section below identifies exactly what is being replaced and why, so it is not mistaken for correct prior art.

---

## What you are REPLACING (the current v1 code — do NOT preserve it)

The v1 implementation currently in `authorize.py` selects the consent template with `if any(s.startswith("clarity."))... elif any(s.startswith("pg."))... elif any(s.startswith("focused."))... else fail`, AFTER `create_authorization_context` has already run. It has three defects (all verified at source) that v2 must eliminate:

1. **Mixed known+unknown bypass.** The full requested scope is stored in the auth context BEFORE the selector. A client registered with `["clarity.write", "widget.read"]` requesting both passes `issubset`, the `any(clarity.)` branch wins, the `else` is never reached, and a code is minted for the FULL scope including `widget.read`. The guard does not block an unknown scope when it is mixed with a known one.
2. **Late rejection leaves a live auth context.** The `else` rejects AFTER `create_authorization_context`, so even a pure-unknown rejected request leaves a valid 10-minute Redis context (its ID logged). v2 must reject BEFORE any context is created.
3. **Mixed cross-app: uninformed consent + wrong audit label.** Per-app branches FILTER `display_scopes` to their own prefix, so a cross-app scope is granted but hidden from the screen; and `consent_ui.py` independently derives the audit app_name by scope-list order, which can disagree with the screen.

Root cause: v1 classifies by `any`-prefix at the wrong pipeline stage. v2 fix: classify each requested scope completely, once, BEFORE any side effect.

---

## Scope of THIS increment (v2)

IN:
- `backend/core/oauth_provider/authorize.py` — replace the `any()`-prefix template selector with complete classification performed BEFORE `create_authorization_context`.
- `backend/core/oauth_provider/consent_ui.py` — stop re-deriving app_name from scope order; reuse the app_name resolved at authorize time (threaded through the auth context).
- Tests for both.

OUT (real issues, but NOT this increment — see "Tracked separately" at end; bundling them turns a focused hardening increment into an auth-system rewrite):
- auth-code + consent-record atomicity
- Redis GET+DEL → atomic GETDEL / one-context-one-code concurrency
- OAuth scope-token grammar validation

NO route changes. NO change to registration. NO change to `clarity/` or the MCP servers.

---

## Canonical guidance (read fresh before implementing)
- `doc/OPERATIONS_PREDEPLOY.md` — read before committing. Shared-backend redeploy + OAuth discovery sanity checks. Mandatory; the focused diff does not waive it.
- Prior art: `claude increments/SHARED ARCHITECTURE/increment_17_oauth_hardening.md`, `inc_oauthperapp.md`.
- **Scope→app facts** were verified against `register_client.py::ROUTE_SCOPE_REGISTRY`, which documents which scopes each app registers with. NOTE: the registry is the REGISTRATION source of truth; it is cited here only as EVIDENCE for the prefix→app facts below. The classification step MUST define its own prefix→app mapping and MUST NOT import or depend on `ROUTE_SCOPE_REGISTRY` at runtime — doing so would introduce a new coupling between the consent path and the registration module. Keep them independent; the registry confirms the facts, it is not a runtime dependency.

---

## Verified facts the design depends on (do not re-derive, but confirm while editing)
- **No current client legitimately spans >1 app prefix.** `ROUTE_SCOPE_REGISTRY`: focused=`["focused.read","focused.write","focused.notify"]` (multi-scope but SINGLE prefix), pg=`["pg.access"]`, mindsort=`["clarity.write"]`. So "reject if scopes span >1 app" is safe — it cannot break a legitimate single-app client. The rule keys on distinct-APP-prefixes, NOT scope count.
- **Focused is DEPRECATED and will never go live.** But it is NOT removed in this increment. The `focused.` classification branch is retained for LEGACY COMPATIBILITY only: the deployed DB may still contain `focused.*`-scoped client rows from earlier testing, the `/oauth/focused/*` routes + `ROUTE_SCOPE_REGISTRY["focused"]` + the `oauth_consent_{lang}.html` template still exist, and `tests/unit/oauth_provider/test_increment_17_consent.py` uses `focused` as its primary fixture app. Keeping the branch means this increment does NOT incidentally break those. Removing Focused is a SEPARATE deprecation-cleanup increment — do not fold it in here. Net effect: keep `focused.` in the classifier; a focused multi-scope set is still ONE app and must NOT be rejected (so the legacy fixtures and any leftover focused clients keep working).
- **App prefixes are exactly three:** `clarity.` → MindSort AI, `pg.` → Priority Guardian, `focused.` → Focused (legacy, deprecated but retained). Anything else = unknown.
- **Registration permits CROSS-APP scopes but NOT unknown scopes.** `register_client.py` validates each requested scope against the union `SUPPORTED_SCOPES` (all known scopes across all apps). So a DCR registration CAN combine known scopes from different apps (e.g. `pg.access clarity.write` — both known) → findings 1/3 (mixed-app) are reachable by a crafted registration. It CANNOT register a scope absent from `SUPPORTED_SCOPES` (e.g. `widget.read`) → the pure-unknown case (finding 2) is NOT reachable via registration today; the unknown-scope guard is therefore defense-in-depth for a future scope added to `SUPPORTED_SCOPES` without a matching consent branch. State this reachability precisely; do not conflate "cross-app" (permitted) with "unknown" (rejected at registration).
- `create_authorization_context(scope=scope)` stores the full scope; auth-context fields are read back in `consent_ui.py`. Threading a new `app_name` field through requires touching `authorization_service.create_authorization_context` signature + the Redis payload + the `consent_ui.py` read. Verify the auth-context schema before adding the field; keep the addition additive (new optional field, default None) so a context written by an older deploy still reads.

---

## Required change (Copy and Adjust, Never Rewrite)

### 1. `authorize.py` — classify once, before auth context (BEHAVIOR, not prescribed structure)

Introduce a single scope-classification step that, given the requested scopes, produces:
- the ONE supported application those scopes belong to, OR a signal that they belong to none / more than one; and
- the set of any requested scopes that match no supported application.

The three supported applications are identified by scope prefix: `clarity.` → MindSort AI, `pg.` → Priority Guardian, `focused.` → Focused (legacy, retained). Any scope matching none of these is unknown. "Spans more than one application" is keyed on the count of DISTINCT applications, NOT the count of scopes (so Focused's legitimate three-scope set is ONE application).

Structure this however best fits the codebase — helper function, inline, whatever is cleanest. Do not over-engineer it. The REQUIREMENT is the behavior and its POSITION in the flow, not a particular function name or shape.

**Position (this is the load-bearing requirement):** the classification AND the rejections below MUST happen BEFORE `create_authorization_context` — i.e. after the existing `issubset` scope validation, before user resolution and context creation — so that a rejected request produces NO Redis auth context and NO other side effect.

Enforce, in order, before context creation:
- **Any unknown scope present** → reject via the endpoint's existing OAuth error mechanism (`_error_redirect` with `invalid_scope`) + a warning log identifying the unknown scopes. (Reject FIRST, before any context.)
- **Else scopes span >1 application** → reject via `_error_redirect` with `invalid_scope` + a warning log identifying the apps. (Multi-app consent is not a supported design.)
- **Else exactly one application** → proceed. Use that application to drive template + `client_name` + `display_scopes`, preserving today's per-app behavior EXACTLY:
  - MindSort AI → `oauth_consent_mindsort_{lang}.html`, client_name `"MindSort AI"`.
  - Priority Guardian → `oauth_consent_pg_{lang}.html`, client_name `"Priority Guardian"`.
  - Focused → `oauth_consent_{lang}.html`, client_name unchanged (current Focused behavior — preserve exactly).

Because unknown and multi-app are already rejected, a single-app request has no cross-app scopes to hide, so `display_scopes` is simply all requested scopes. (This also removes v1's per-app `display_scopes` filtering, which only existed to paper over the mixed case that is now rejected outright.) Choose two distinct, greppable log event names for the unknown-scope and multi-app rejections so the first real occurrence of each is visible in Better Stack.

**Thread the resolved application name into the auth context** so the consent POST reuses it instead of re-deriving (see #2, #3).

### 2. `authorization_service.create_authorization_context` — accept + store `app_name` (BACKWARD-COMPATIBLE, HARD REQUIREMENT)
Add an optional `app_name: str | None = None` parameter; include it in the Redis payload when present.

**Rolling-deployment invariant (hard requirement, not a nice-to-have):** the shared backend deploys as a rolling update, so during the deploy window BOTH version-mix directions occur and BOTH must be safe:
- **Old authorize → new consent:** a context written by the OLD code has NO `app_name` key. The NEW `consent_ui.py` MUST handle a missing/None `app_name` without error (it falls back — see #3). This is the common case during deploy and MUST work.
- **New authorize → old consent:** a context written by the NEW code carries an EXTRA `app_name` key. The OLD `consent_ui.py` reads named fields and ignores extras, so this must be harmless — confirm the old read path does not choke on an unexpected key (it should not; verify the deserialization is field-named, not positional/strict-schema).
The field MUST be purely additive: no rename, no type change, no removal of existing context fields, no change that an in-flight older context could not satisfy. Older contexts without `app_name` must keep working until they naturally expire (10-min TTL).

### 3. `consent_ui.py` — reuse `app_name`, don't re-derive
- Read `app_name` from the auth context. If present, use it directly for `record_consent`.
- If absent (older context written before this deploy, during the deploy window) → fall back to the EXISTING `_derive_app_name_from_scopes`, but with its unmatched return changed from `"focused"` to `"unknown"` (audit accuracy) — keep this fallback solely for in-flight contexts; it should be rare and short-lived.
- Keep the warning log if the resolved app_name is `"unknown"` (defense in depth), still record (never block) — the role-asymmetry from v1 stands: the RECORDER never blocks; a minted token must always get a consent record.

This makes the consent screen (authorize) and the audit record (consent) use the SAME `app_name` by construction — closing finding 3's screen-vs-audit divergence at the root rather than hoping two independent derivations agree.

---

## What NOT to do
- Do NOT classify or reject AFTER `create_authorization_context`. The whole point of v2 is rejecting before side effects.
- Do NOT reject a focused multi-scope set (`focused.read focused.write focused.notify`) — that is ONE app. Key on distinct app prefixes, not scope count. (Focused is deprecated, but legacy fixtures + possibly leftover DB clients still exercise this path; rejecting it would break `test_increment_17_consent.py`.)
- Do NOT remove the `focused.` branch, the `/oauth/focused/*` routes, the focused registry entry, or the focused template — Focused deprecation/removal is a SEPARATE increment, not this one.
- Do NOT touch registration, routes, `clarity/`, MCP servers, discovery.
- Do NOT fix atomicity / GETDEL concurrency / scope-grammar here (tracked separately).
- Do NOT block in `consent_ui.py` — it records, never rejects.

---

## Tests

### authorize.py classification (unit — the classification logic, however structured)
1. Single-app sets resolve correctly: `{clarity.write}`→MindSort,no-unknown; `{pg.access}`→PG,no-unknown; `{focused.read,focused.write,focused.notify}`→Focused,no-unknown. *Catches:* Focused multi-scope wrongly treated as multi-app.
2. Unknown present: `{clarity.write, widget.read}`→ unknown includes `widget.read`. *Catches:* the v1 mixed known+unknown bypass.
3. Multi-app: `{pg.access, clarity.write}`→ "spans multiple apps" (no single app). *Catches:* cross-app not detected.
4. Pure unknown: `{widget.read}`→ unknown, no app; empty set→ no app, no unknown. *Catches:* unknown-vs-multiapp conflation.

### authorize.py endpoint (integration, real DB client + real flow)
**Test-client construction — read this first (avoids a contradiction with verified DCR behavior):** normal Dynamic Client Registration (`register_client.py`) validates each scope against `SUPPORTED_SCOPES` and will REJECT an unknown scope like `widget.read`. So a client holding `widget.read` CANNOT be created through the DCR endpoint. For tests that need such a client (5, 7), insert the client row DIRECTLY into the test DB (a synthetic fixture that BYPASSES DCR) — this is legitimate: the authorize-time guard must hold even for a client that should not exist, which is exactly the defense-in-depth being tested. Do NOT attempt to register these via the `/register` endpoint; that would fail at registration and you'd be testing the wrong layer. By contrast, test 6's `["pg.access","clarity.write"]` IS registerable through normal DCR (both scopes are known) — register it the normal way (or via the same DB fixture, but note it as DCR-legal); it is the genuinely-reachable mixed-app case.

5. **Mixed known+unknown → invalid_scope, AND no auth context created.** Synthetic client (DIRECT DB insert, bypasses DCR) with `scopes=["clarity.write","widget.read"]`; request both, assert 302 `invalid_scope`. Then assert NO Redis auth context was created for this request (the v1 ordering defect — context created before rejection). *Catches:* findings 1 AND 2 together. (To assert "no context": spy/patch `create_authorization_context` and assert NOT called, OR assert the Redis store has no new key — patch-and-assert-not-called is simplest and directly encodes "rejection precedes context creation".) State in the test that the client is a synthetic DB fixture, since `widget.read` is not DCR-registerable.
6. **Multi-app → invalid_scope, no context.** Client with `["pg.access","clarity.write"]` (DCR-LEGAL — both known; this is the genuinely reachable mixed-app case). Request both → 302 `invalid_scope`, `create_authorization_context` NOT called. *Catches:* finding 3 at the gate.
7. **Pure unknown → invalid_scope, no context, warning logged** (`consent_unknown_scope` via caplog). Synthetic client (DIRECT DB insert, bypasses DCR) with `scopes=["widget.read"]`; request `widget.read`. *Catches:* the ordering fix + the unknown guard. State in the test that the client is a synthetic DB fixture, since `widget.read` is not DCR-registerable (so this case is defense-in-depth, not normally reachable).
8. **Each single app still renders its screen** (clarity→MindSort, pg→PG, focused→Focused) with correct client_name — real HTML assertions. These clients ARE DCR-legal (single-app, known scopes); register normally or via DB fixture. *Catches:* the classification refactor breaking the happy path. (Test 8-focused is the critical non-regression: Focused multi-scope must still render, not be rejected as multi-app.)

### consent_ui.py app_name reuse (integration through real consent_endpoint)
9. **app_name threaded from context is used for the audit record.** Auth context carrying `app_name="mindsort"` + scope `clarity.write` → `record_consent` called with `app_name="mindsort"`, NOT re-derived. *Catches:* the screen-vs-audit divergence (finding 3's recorder half) — proves the record uses the authorize-resolved app, not an independent scope-order derivation.
10. **Fallback path:** context with `app_name=None` (older deploy) + unknown scope → `_derive_app_name_from_scopes` returns `"unknown"` (not `"focused"`), consent recorded under `"unknown"` + warning logged, flow completes (302). *Catches:* the in-flight-context fallback regressing to `"focused"` or blocking.

For each test, document "what bug would still pass this test?"

---

## Production readiness
- **GDPR/consent integrity:** core value — the consent screen and the audit record now use the SAME resolved app_name by construction; unknown and multi-app scopes are rejected before any token/context side effect.
- **Rolling-deployment safety (explicit invariant):** the `app_name` auth-context field is purely additive. Old-authorize→new-consent (missing field → fallback) MUST work; new-authorize→old-consent (extra field → ignored) MUST be harmless. No in-flight 10-min context may be invalidated by this deploy. This is the production gate for the schema change, verified by test 10 (fallback path) plus the old-read-path confirmation in #2.
- **DB integrity:** none new (`app_name` still free-text `String(50)` per CoreConsent — verified; `"unknown"` safe).
- **Security:** strictly tighter — closes a scope-grant bypass and removes a pre-rejection side effect.

## Definition of Done
- [ ] Classification + both rejections (unknown, multi-app) happen BEFORE `create_authorization_context`; a rejected request creates NO auth context.
- [ ] Mixed known+unknown rejected (invalid_scope, no context); multi-app rejected (invalid_scope, no context); pure unknown rejected + warning.
- [ ] Focused multi-scope still renders (NOT rejected); clarity/pg/focused single-app screens unchanged.
- [ ] **Valid single-app OAuth flows for PG and MindSort are unchanged** — same template, same client_name, same granted scopes, same success redirect as before this increment. This increment hardens INVALID requests without altering VALID ones; prove it (tests 8 + the byte-for-byte intent of the single-app assertions).
- [ ] `app_name` threaded through `create_authorization_context` (additive, backward-compatible per the rolling-deploy invariant) and reused in `consent_ui.py`; `_derive_app_name_from_scopes` retained ONLY as the missing-`app_name` fallback, returning `"unknown"` (not `"focused"`) for unmatched.
- [ ] Classification does NOT import `ROUTE_SCOPE_REGISTRY` (no new coupling to the registration module).
- [ ] Tests 1–10 pass; each documents the bug it catches; the two "no context created" assertions (tests 5, 6) are present and real.
- [ ] Full `pytest tests/unit/ --ignore=tests/unit/mcp_focused -q`: known-baseline unchanged.
- [ ] No change outside the three files + tests.
- [ ] Before commit: read `OPERATIONS_PREDEPLOY.md`.

## Post-deploy verification (deployer; shared backend — BOTH platforms, per inc_06 discipline)
1. Live ChatGPT consent (PG or MindSort) still renders correct branded screen.
2. Live Claude consent (MindSort-Claude, delete+re-add) still renders MindSort screen.
(Focused is deprecated/never-live, so no live Focused consent check is needed — but the classifier still keeps its branch for legacy DB/test compatibility, verified by the test suite, not by a live check.)

## Not verified by this briefing (state in review)
- The exact auth-context (de)serialization path for the new `app_name` field — implementer must confirm `create_authorization_context` and the `consent_ui.py` read handle the additive field and a missing key (older context) without error.
- Whether any test/CI fixture registers a cross-app client that these new rejections would now break — grep fixtures for multi-prefix `scopes=[...]` before finalizing; if one exists, it was relying on the v1 hole and must be updated, but confirm it's a test artifact and not a real client pattern.

---

## Tracked separately (real findings, NOT this increment)
Open as their own increments; do not bundle:
1. **Auth-code + consent-record atomicity** — `create_authorization_code` commits, then `record_consent` commits later; a failure between leaves a valid unused code with no consent record. Prefer one transaction or record-consent-first. (Pre-existing, Increment 12/17 era.)
2. **Redis context consumption not atomic** — `get_authorization_context` does GET then DELETE, not GETDEL; two concurrent consent POSTs can both read one context and mint two codes. Token-replay protection only covers duplicate exchange of the SAME code, not two distinct codes from one context. Highest-value of the three; own increment soon. (Pre-existing.)
3. **OAuth scope-token grammar validation** — `scope.split()` normalizes whitespace but no RFC 6749 scope-token grammar check; malformed registered scopes (`focused.`, control chars, over-length) can pass prefix checks or fail `CoreConsent.scope` length after code commit. (Pre-existing.)
