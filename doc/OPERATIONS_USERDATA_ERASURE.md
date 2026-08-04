# Operations — Data Erasure Runbook

**Scope:** handling data-subject erasure requests for the Priority Guard Suite.
**Audience:** whoever answers `support@priority-guard.com`. Currently Nadja.
**Related:** `ADR_008_data_ownership_and_deletion_model.md` (the decisions),
`ADR_007_user_identity_and_lifecycle.md` (why identification works or doesn't),
`ADR_006_token_revocation_semantics.md` (disconnect vs deletion),
`legal/pg_data_retention_and_permission_surface.md` (retention periods).

---

## 0. The one-paragraph version

Almost every erasure request should be answered by telling the user to delete their data
**inside the app**, where they are already authenticated. That is Operation A and it is the
supported path. Operation B — erasing a user across the whole suite — is **not implemented**
and must not be improvised. If a request cannot be satisfied by Operation A, record it,
start the 30-day clock, fulfil what you can, and say plainly what remains outstanding.

---

## 1. The two operations

| | **A — Delete Priority Guardian data** | **B — Delete all Priority Guard Suite data** |
|---|---|---|
| Trigger | User asks, in-app | Support request |
| Mechanism | `delete_my_priority_guardian_data` MCP tool | **None — not implemented** |
| Scope | PG-owned data + PG-scoped rows in shared tables | Every app's data + `core_users` |
| Status | **Supported** | **Do not attempt** |

---

## 2. Operation A — the answer to almost every request

**If the user can still reach Priority Guardian in ChatGPT or Claude, direct them to use the
in-app deletion. That is the whole procedure.** They are already authenticated, so there is
no identification problem (ADR_007 §5): the JWT's `sub` resolves to their `CoreUser`.

Wording that works:

> You can delete your Priority Guardian data yourself, right where you use it. Ask Priority
> Guardian to "delete my Priority Guardian data" and confirm when prompted. It removes your
> priorities, goals, deliverables, weekly progress history, your Google Calendar connection
> and your Priority Guardian sign-in data. Your other Priority Guard apps aren't affected —
> a MindSort AI board stays exactly as it is.

### What it removes

Priorities, goals, deliverables, weekly progress snapshots, the Google Calendar connection
(revoked at Google), PG consent records, and PG access tokens and authorization codes.

### What it deliberately keeps, and why

| Retained | Why | For how long |
|---|---|---|
| A security audit record of the deletion | Proof the erasure happened. Deliberately not linked by foreign key so it survives (ADR_008 §3) | 90 days, swept by `cleanup_expired_audit_logs` |
| The shared sign-in identity (`core_users`) | Other suite apps hang off it. Deleting it would destroy a MindSort user's board (ADR_008 §2) | Until the 6-month inactivity cleanup, or Operation B |
| The browser session (`oauth_sessions`) | Suite-level, not PG state. PG-scoped deletion is not account deletion (`pg_data_retention_and_permission_surface.md` §10.1) | 30-day sliding expiry |
| Encrypted database backups | Deletion removes data from active storage, not from backups | 7 days, then automatically and permanently deleted |

### Two things to be accurate about if asked

**Backups.** Deleting does not reach into backups. They expire on their own within 7 days.
Say this plainly rather than implying instant total erasure.

**Access does not stop at the same instant.** Priority Guardian's servers validate tokens
against signing keys without a database lookup, so a token already issued stays valid until
it expires — up to **60 minutes 30 seconds** at current settings (ADR_006). The data is
already gone, so nothing can be read; but do not tell a user access was "immediately
terminated". If they want the connection severed as well, they should also disconnect the app
in ChatGPT or Claude.

---

## 3. Operation B — record it, do not perform it

**Suite-wide erasure is not implemented, and this runbook deliberately does not specify a
procedure for it.**

An earlier draft gave a three-step sequence — delete PG data, delete MindSort data, then the
`core_users` row. **That was under-verified and has been removed.** A correct suite-wide
erasure needs its own verified inventory covering every published and deprecated app, shared
consents, all OAuth grants and sessions, shared connections, audit retention, Redis,
scheduled jobs and backups. That work has not been done.

**When a request arrives that Operation A cannot satisfy:**

1. **Record the request and the date.** The 30-day clock starts now (§4).
2. **Do NOT delete the `core_users` row.** It cascades to every app in the suite. A user who
   asked about Priority Guardian would lose their MindSort board, irreversibly.
3. **Fulfil the PG-scoped portion via Operation A** if the user can still reach the app.
4. **Tell the requester what remains outstanding**, honestly, and that you will confirm when
   it is complete.

> Operation B is not yet implemented. Record the request and the 30-day clock. Do **not**
> delete `core_users` until a verified suite-wide erasure procedure exists. Fulfil the
> PG-scoped portion via Operation A and tell the requester what remains outstanding.

---

## 4. The 30-day clock

The published privacy policy commits to responding to data-subject requests **within 30
days**, per GDPR Art. 12(3). The clock starts when the request arrives, not when you begin
working on it.

The six-month inactivity cleanup is **not** how a request gets fulfilled. It is a retention
backstop. It can also never fire for a user who still has an active consent on another suite
app, so it may never run at all for the person asking.

---

## 5. Identifying a requester who cannot reach the app

**This is the hard case, and it is deliberately not a deterministic procedure.**

`CoreUser` stores only an internal id, platform identifiers, and timestamps — **no email and
no name.** This is data minimisation working as intended, and it is why an emailed request
carries no field that maps reliably to a row (ADR_007 §5).

**Investigate case by case.** Use whatever the requester can supply, weigh it, and record
what you concluded and why.

**Do NOT ask them to confirm priority names or calendar keywords as proof of identity.** This
was considered and explicitly rejected (ADR_008 §6): a priority called "Prepare presentation"
or a keyword `P1` is not a secret, is guessable, and is not a defensible verification
standard. Presenting a heuristic as a verification mechanism is worse than admitting the
limit.

**It is legitimate to conclude you cannot identify the record.** Say so:

> Because the service stores only pseudonymous user records, we may need additional
> information to identify the correct account, and in some cases we may not be able to link a
> request to a record.

That wording is agreed in ADR_008 §5 and must match what the published policy says.

### Why this cannot be fixed by asking for more identifiers

Every mechanism that would make the email channel deterministic was considered and rejected
or deferred (ADR_008 §6) — a user-visible support id, collecting the Google account email,
first-party identity. The conclusion that made them unnecessary: **the gap was never
identity, it was a missing authenticated deletion operation.** That operation now exists, and
it is Operation A.

---

## 6. Escalation triggers

Stop and think rather than proceeding if:

- The request is for suite-wide erasure → §3, record and report, no deletion of `core_users`
- The requester cannot be identified with confidence → §5, and it is acceptable to say no
- The request concerns an app other than Priority Guardian → MindSort has its own
  board-scoped deletion; there is no account-scoped deletion for it (ADR_008 §7.2)
- A regulator or DPA is involved → the 30-day clock and written records matter more than speed
- The deletion tool reports a failure → it is explicitly retryable and nothing was deleted;
  retry before escalating

---

## 7. What this runbook does not cover

- **Suite-wide erasure (Operation B).** Not implemented. §3.
- **Data export / portability.** The same identification limits apply; an authenticated
  export tool is recorded as open work in ADR_008 §7.3.
- **Deletion for MindSort account data.** `delete_my_data` there deletes a board, not an
  account (ADR_008 §7.2).
