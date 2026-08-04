# ADR_007 — User Identity and Lifecycle

**Date:** 2026-08-01
**Status:** Accepted (documents existing behaviour; contains no new engineering decision)
**Supersedes in part:** `doc/OAuth/oauth_user_identity.md` (2026-03-14) — see §7

---

## Context

This ADR was written after an OAuth review surfaced a question that looked like a deletion
problem and turned out to be an identity problem: *when a user asks us to delete their data,
how do we know which rows are theirs?*

The answer differs by platform, and the difference is **not** a design choice we made. It is
determined entirely by what each platform exposes to a third-party MCP server.

Everything below is verified from source at the paths cited. Nothing is inferred from
documentation or briefings.

---

## 1. Decision — canonical identity

**`CoreUser.id` (UUID) is the canonical application identity.** Every foreign key in the
suite points at it. `backend/core/models.py` states it directly: *"The internal UUID `id` is
the canonical reference used by all FKs."*

**Platform identifiers are opportunistic mappings, not the identity.** They are used to
*resolve* to a `CoreUser` when available. They are not relied upon for correctness, and their
absence degrades continuity rather than breaking the system.

This wording matters: `CoreUser.id` is canonical *by construction* — it is what the data hangs
off. It is **not** globally stable across a user's lifetime, because a single human can end up
with more than one `CoreUser` row (§4).

---

## 2. How identity is resolved — two stages

### Stage 1 — OAuth authorize time
`backend/core/oauth_provider/authorize.py::_resolve_user_identity`, three paths in priority order:

| # | Path | Status |
|---|---|---|
| 1 | `login_hint` → `CoreUser.chatgpt_user_id` | **Dead in production.** ChatGPT does not send it. Every `oauth.authorize.request` logs `has_login_hint: false`. Implemented and correct; never executes. |
| 2 | `pg_session` cookie → `oauth_sessions.user_id` | Works within one browser. 30-day sliding window. Token stored SHA-256 hashed; plaintext never persisted (`session_service.py`). |
| 3 | Neither → create a new anonymous `CoreUser` | Fires on new browser, cleared cookies, incognito, or expired session. |

### Stage 2 — every tool call (ChatGPT only)
`mcp_server/priority_guardian/mcp_auth.py::authenticate_request` calls
`reconcile_user_via_backend()` **after** JWT validation and **before** scope enforcement.

**The JWT's `sub` is provisional.** Reconciliation may return a different, canonical
`user_id`, and that is what every downstream handler receives.

---

## 3. ChatGPT — solved by Increment 78

ChatGPT supplies `_meta["openai/subject"]`, an anonymized per-user identifier, on tool calls.
`CoreUser.openai_subject` (`String(128)`) stores it under a **partial unique index**
(`WHERE openai_subject IS NOT NULL`), enforcing one subject → one `CoreUser`.

`backend/apps/priority_guardian/routers/reconcile_router.py` implements the contract:

| Case | Condition | Result |
|---|---|---|
| **A** | Subject unbound | Guarded `UPDATE ... WHERE openai_subject IS NULL` stamps it onto `jwt_user_id` |
| **B** | Subject owned by `jwt_user_id` | Steady state, no change |
| **C1** | Subject owned by another user **and** `jwt_user_id` is a fresh shell | Return the canonical owner — this is the cross-device fix |
| **C2** | Subject owned by another user **and** `jwt_user_id` has state | **Refuse the swap.** Logged at ERROR. |
| **X** | Guarded update lost the race and re-lookup found no owner | Return `jwt_user_id`. Logged at ERROR for paging. |

**Fresh-shell invariant (C1 vs C2):** a `CoreUser` is a fresh shell only when it has *no active
non-revoked Google connection* **and** *no `PgPriority` of any status*. **When a new PG-owned
state table is added, this check must be extended** — otherwise a user with state in the new
table is wrongly classified as a shell and silently remapped. See the warning at the top of
`doc/OPERATIONS_MIGRATIONS.md`.

**Design properties worth preserving:**
- The MCP server holds no database access; all reconciliation state lives in the backend.
- Reconciliation **degrades gracefully** — absent subject or backend failure returns
  `jwt_user_id` unchanged and logs a warning. It never blocks a tool call.
- Unknown case values are logged at ERROR as contract drift.
- C2 refuses rather than guesses. Losing continuity is preferable to merging two real users.

**Net effect:** a new browser still creates an anonymous `CoreUser` at authorize time, but the
first tool call reconciles it onto the existing user. ChatGPT identity is effectively stable
across browsers and devices.

---

## 4. Claude — no platform identifier exists

Anthropic exposes **no** Claude account subject to third-party MCP servers.

**Verified 2026-08-01 against the primary source:**
`https://claude.com/docs/connectors/building/authentication` documents the complete auth
surface — six authentication types, DCR, CIMD, Anthropic-held credentials, callback URLs,
token refresh, enterprise auth, latency limits, egress range. **Nothing in it exposes a user
identifier to the connector.** Two statements make this explicit rather than merely absent:

> *"Directory connectors use a **single shared OAuth application per connector**. There is no
> per-org OAuth client for directory connectors."*

so `azp` identifies the connector, not the user; and, from Anthropic's own framing of authless
servers, *without auth Claude does not send an application user ID to the MCP server at all* —
identity is expected to come from **your** authorization server.

The `_meta` fields Anthropic does define for MCP servers are behavioural
(`anthropic/requiresUserInteraction`, `anthropic/alwaysLoad`). None carries identity.

`mcp_server/priority_guardian_claude/mcp_auth_dupl.py` therefore has **no reconciliation step**
— there is no signal to reconcile against. Identity is the OAuth grant: JWT `sub` →
`CoreUser.id`, and nothing more.

**What works:** every authenticated operation. One grant serves claude.ai web, desktop and
mobile, because the token is held against the Claude account. Verified empirically 2026-08-01 —
the same data loads on desktop and iPhone.

**What does not:** continuity across a *re-authorization* where the `pg_session` cookie is
absent. Full connector removal, cookie loss, a different browser, or expiry past 30 days each
produce a new `CoreUser`. The prior data still exists but is unreachable — nothing links the
two rows.

**This is a platform constraint, not a defect to fix.** No amount of local architecture
produces a stable Claude identity when the platform exposes none.

---

## 5. Consequence per operation

| Operation | ChatGPT | Claude |
|---|---|---|
| Authenticated tool call | Canonical via reconciliation | Canonical via grant |
| In-app deletion / export | Works — `sub` resolves the user | Works — `sub` resolves the user |
| Reconnect after cookie loss | Recovered via `openai/subject` | **Not recoverable** — new `CoreUser` |
| Email request from a connected user | Resolvable if they can supply a signal | Same |
| Email request from a disconnected user | **Not resolvable** | **Not resolvable** |

**The single sentence that explains all of it:** *authenticated operations resolve identity
correctly; unauthenticated operations cannot be reliably matched to a user.*

`CoreUser` stores only `id`, `chatgpt_user_id`, `openai_subject`, `created_at` — **no email,
no name.** An emailed request carries no field that maps to a row. This is deliberate data
minimisation, not an oversight, and it is why the email channel is structurally weak.

**Note on `openai_subject`:** it is stable and unique, but it is an opaque value OpenAI
generates. The user has never seen it and cannot quote it. It solves machine-to-machine
continuity; it does **not** solve human-to-support identification.

---

## 6. The email channel — decided in ADR_008

An earlier draft of this ADR left this open. It has since been decided:

**Authenticated in-app deletion is the primary channel. Email is exceptional and best-effort.**

See `doc/ADR_008_data_ownership_and_deletion_model.md` §5 for the decision, the rejected
alternatives, and the agreed policy wording. The conclusion that made the alternatives
unnecessary: every proposed identity mechanism existed to make the *email* channel
deterministic. Once email is not the primary channel, none is needed.

---

## 7. Known limitations

1. **Duplicate `CoreUser` rows accumulate.** Every abandoned authorize that reaches path 3
   leaves an orphan row. Mitigated by six-month inactivity cleanup
   (`backend/jobs/retention_cleanup.py`), which is a retention control — **not** a substitute
   for a requested erasure.
2. **Fresh-shell check must be extended with new state tables** (§3).
3. **No auto-merge rule:** never merge two `CoreUser` rows on the basis of the same browser,
   similar priorities, an email claim, or an inferred human identity. Merge only on a stable
   platform identifier or proven control of both. C2 already encodes this.
4. **`doc/OAuth/oauth_user_identity.md` is stale.** Dated 2026-03-14, it describes ChatGPT
   identity fragmentation as an open structural problem. Increment 78 postdates it and largely
   resolves it. Supersession notes have been added in place.
5. **PG has no user-initiated deletion path.** `priority_guardian/routers/offboarding_router.py`
   exposes `/disconnect` only. Addressed by the PG authenticated-deletion increment; see
   ADR_008.

---

## 8. Rejected alternatives

**A `PlatformIdentity` join table** (`platform`, `external_subject`, `identity_type`,
`verified_at`). Rejected: two platforms, only one supplies a subject, so the table would hold
one meaningful row type. `CoreUser` already carries `chatgpt_user_id` and `openai_subject` as
columns. Revisit only if a third platform arrives, or if `openai/subject` is observed to
rotate and multiple historical subjects per user become necessary.

**A user-visible support ID** (keyed hash of `user_id`, displayed in the widget, quoted in
emails). Technically sound and solves email identification. Rejected on product grounds:
*settings → copy identifier → paste into email → wait* is bureaucratic, and it only helps
users who can still open the app — who could use the in-app tool instead.

**Collecting the Google account email.** Rejected — see ADR_008 §6.

**First-party identity for Claude** — magic link or passkey at the consent screen. This is the
only mechanism that gives Claude durable cross-disconnect continuity. **Deferred, not
rejected.** Costs: onboarding friction, collecting an email or credential, additional GDPR and
security obligations, account recovery and abuse controls. Revisit if users report losing data
after reconnecting, or if persistent priorities must survive full disconnection.

---

## 9. Revisit triggers

- `openai/subject` observed to rotate for a stable user
- Anthropic exposes a per-user identifier to MCP servers
- Case C2 or X appearing at material volume in production logs
- A new PG-owned state table added without extending the fresh-shell check
- Users reporting data loss after reconnecting on Claude

---

## 10. Cross-references

- `doc/ADR_008_data_ownership_and_deletion_model.md` — deletion model, email decision
- `doc/ADR_006_token_revocation_semantics.md` — disconnect/deletion trigger table
- `doc/OAuth/oauth_user_identity.md` — pre-Inc-78 analysis; superseded in part, see §7.4
- `doc/OPERATIONS_MIGRATIONS.md` — the fresh-shell warning
- `backend/apps/priority_guardian/routers/reconcile_router.py` — the reconciliation contract
- `backend/core/models.py` — `CoreUser`, the partial unique index on `openai_subject`

---

## What Claude Code must know

1. **`CoreUser.id` is canonical. Never key application data on a platform identifier.**
2. **On ChatGPT, use the reconciled `user_id` from `authenticate_request()`** — not the raw
   JWT `sub`. They can differ, and the reconciled value is the correct one.
3. **Adding a PG-owned state table requires extending the fresh-shell check** in
   `_reconcile_user_by_subject`. Missing it causes silent wrong-user remapping.
4. **Never delete `core_users` rows in app-scoped deletion.** Shared across the suite.
5. **Never auto-merge `CoreUser` rows.** C2 refuses deliberately; preserve that behaviour.
6. **Claude has no subject and no reconciliation.** Do not add a reconciliation call to the
   Claude path expecting a signal that does not exist.
