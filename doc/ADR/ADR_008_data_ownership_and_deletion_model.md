# ADR_008 — Data Ownership and Deletion Model

**Date:** 2026-08-01
**Status:** Accepted
**Related:** `ADR_007_user_identity_and_lifecycle.md` (identity), `ADR_006_token_revocation_semantics.md` (disconnect vs deletion)

---

## Context

Priority Guardian has no user-initiated deletion path on either platform.
`backend/apps/priority_guardian/routers/offboarding_router.py` exposes `/disconnect` only,
and its docstring records the omission: *"No DELETE /delete-data yet (later increment)."*
MindSort ships `delete_my_data`, which deletes a **board**, not an account.

The published privacy policy routes erasure to `support@priority-guard.com`. That route cannot
be reliably executed, because `CoreUser` stores no email and no name — an emailed request
carries no field that maps to a row (ADR_007 §5).

This ADR records the deletion model and the identification model that were agreed after
working through the alternatives. It documents decisions; the implementing increment is
separate.

---

## 1. Decision — data ownership

Every table has exactly one owner. **A deletion operation may only delete data owned by its
own application, unless the user explicitly requests suite-wide deletion.**

| Data | Owner | On PG deletion |
|---|---|---|
| `core_users` | **Suite** | **Retained** — see §2 |
| `pg_priorities` | PG | Delete |
| `pg_goals` | PG (via `pg_priorities`) | Delete |
| `pg_deliverables` | PG (via `pg_priorities`) | Delete |
| `pg_weekly_snapshots` | PG | Delete |
| `core_connections` (Google) | PG (in PG context) | Revoke at Google, then delete |
| `core_consents` (PG scopes) | PG | Delete PG-scoped rows only |
| `oauth_access_tokens` (`pg.access`) | PG | Revoke, then delete |
| `oauth_sessions` | Suite | **Retained** — browser session, not PG state |
| `core_tool_audit_log` | Suite | **Retained** — see §3 |
| MindSort board data | MindSort | **Never touched** |

**The inventory above is a reconstruction from reading `backend/apps/priority_guardian/db_models.py`
and `backend/core/models.py`. It MUST be verified against the live schema before implementation.**
Any table added since, or missed, breaks the contract. Verification is Part A of the
implementing increment.

---

## 2. Why `core_users` is retained

**The justification is architectural, not legal.**

`core_users` is shared infrastructure. `core_users.id` is the anchor for every app in the
suite, and every dependent table cascades from it (`ondelete="CASCADE"`). Deleting the row as
part of a *per-application* deletion request would silently erase data belonging to other
applications the user did not ask to delete — a MindSort user who deletes their Priority
Guardian data would lose their board.

`backend/apps/focused/logic/offboarding.py::delete_user_data` already encodes this rule:
*"Does NOT delete core_users row (shared across SDK apps)."* PG follows the same pattern.

**An earlier draft justified retention on the grounds that a residual `CoreUser` row — a bare
UUID with no content — is arguably no longer personal data under GDPR Recital 26. That
argument is deliberately NOT the basis for this decision.** It is a legal interpretation, not
an engineering fact, and the architecture must not depend on it. The residual row is treated as
potentially personal data; whether its retention is additionally justified is a question for
legal review (§7.1).

The architectural justification stands on its own and is the one to cite.

**Consequence:** a PG-only user's `CoreUser` row survives PG deletion as an empty shell until
the six-month inactivity cleanup (`backend/jobs/retention_cleanup.py`) removes it. That is a
retention control on a row with no content, not a delayed erasure of user data.

---

## 3. Why `core_tool_audit_log` is retained

Deliberately not a foreign key. The column comment states the reason: *"audit logs must persist
after user deletion for GDPR compliance."* Rows expire independently at 90 days via
`cleanup_expired_audit_logs`, and the published privacy policy already discloses this separate
retention. The deletion operation **writes** an entry here; it does not remove them.

---

## 4. Decision — two distinct operations

| | **A — Delete my Priority Guardian data** | **B — Delete all my Priority Guard Suite data** |
|---|---|---|
| Trigger | Authenticated MCP tool | Support request, manual runbook |
| Scope | PG-owned data per §1 | Every app's data + `core_users` |
| Frequency | Normal path | Rare |
| Implementation | The deletion increment | Runbook only — no tool |

**Naming is load-bearing.** The tool is *"delete my Priority Guardian data"*, never *"delete my
account"*. A user who typed "delete my account" and later found their MindSort board gone
would be right to object. The tool description must state that other Priority Guard apps are
unaffected.

Operation B is rare enough not to need a tool and common enough to need a documented
procedure: run PG deletion, run MindSort deletion, then delete the `core_users` row.

---

## 5. Decision — how the requester is identified

**Primary channel: authenticated, in-app.** The JWT carries `sub`, which resolves to
`CoreUser.id` — on ChatGPT via reconciliation (ADR_007 §3), on Claude directly from the grant
(ADR_007 §4). **There is no identification problem on this path.** The user is already
authenticated; nothing further is required.

**Secondary channel: support email, exceptional and best-effort.** For a user who can still
reach the app, support directs them to the in-app tool. For a user who cannot, support
investigates case by case and may be unable to identify the record.

**Support investigation is deliberately not specified as a deterministic procedure.** Earlier
drafts proposed asking the requester to confirm priority names or calendar keywords. Those were
**rejected**: a priority named "Prepare presentation" or a keyword `P1` is not a secret, is
guessable, and is not a defensible verification standard. Case-by-case investigation is
legitimate for a rare support path; presenting heuristics as a verification mechanism is not.

**The policy must not promise what this cannot deliver.** Agreed wording shape:

> The primary way to delete your Priority Guardian data is inside the app while connected. If
> you no longer have access, contact support. Because the service stores pseudonymous user
> records, we may need additional information to identify the correct account, and in some
> cases we may not be able to link a request to a record.

---

## 6. Rejected alternatives

Each was considered and rejected. Recorded so they are not re-proposed.

| Alternative | Why rejected |
|---|---|
| **User-visible support ID** (keyed hash of `user_id`, shown in the widget, quoted in emails) | Technically sound; poor product. *Settings → copy identifier → paste into email → wait* is bureaucratic, and it only helps users who can still open the app — who could simply use the in-app tool instead. |
| **Collect the Google account email** (add `userinfo.email` scope) | Solves lookup, not ownership verification — knowing an address does not prove the sender controls the account. Adds directly identifying data to a system that currently holds none, reversing data minimisation. Covers only Calendar-connected users. Requires all existing users to reconnect before any email exists. `userinfo.email` is a separate Google scope from Calendar and changes the consent screen. |
| **First-party identity** (magic link, passkey, federated sign-in at the consent screen) | The only mechanism giving Claude durable continuity across full disconnection. **Deferred, not rejected.** Costs: onboarding friction, personal-data storage, recovery flows, abuse controls. Revisit only if users demonstrably need continuity across complete disconnects. |
| **Canonical-identity architecture project** (`PlatformIdentity` table, redesigned identity model) | Solves a problem that does not exist. Identity is already resolved for authenticated users. See ADR_007 §8. |
| **Six-month inactivity cleanup as the erasure mechanism** | It is a retention backstop, not request fulfilment. Art. 12(3) requires response without undue delay; the published policy commits to 30 days. It can also never fire for a user with an active consent on another suite app. |

**The conclusion that made the alternatives unnecessary:** every one of them existed to make the
*email* channel deterministic. Once email is not the primary channel, none is needed. The gap
was never Claude identity — it was a missing authenticated deletion operation.

---

## 7. Open items

1. **Legal review of residual `CoreUser` retention.** The architectural justification (§2) is
   sound. Whether retaining a content-free pseudonymous row is additionally defensible under
   GDPR should be confirmed by a data protection advisor. **Not a blocker** — the row is
   retained because other apps require it, which is an independent and sufficient reason.
2. **MindSort scope inconsistency.** `delete_my_data` deletes a board, not MindSort's account
   data. After the PG increment, PG has account-scoped deletion and MindSort does not. Separate
   increment.
3. **Privacy policy §9 (export) has the same gap as §10 (deletion).** An emailed JSON export
   faces the identical identification problem. Either scope it the same way or implement an
   authenticated export tool.
4. **Verify the §1 inventory against the live schema** before implementing.

---

## What Claude Code must know

1. **Never delete `core_users` in an app-scoped deletion.** Shared across the suite; cascading
   it destroys other apps' data.
2. **Never delete `core_tool_audit_log` rows.** They are the record that deletion happened, and
   they expire on their own schedule.
3. **Delete only PG-scoped rows** from shared tables (`core_consents`, `oauth_access_tokens`) —
   filter by scope, never by `user_id` alone.
4. **`backend/apps/focused/logic/offboarding.py::delete_user_data` is the reference
   implementation.** Copy the pattern; adapt the tables. Do not redesign it.
5. **Name the tool for what it does.** PG data, not "account".
