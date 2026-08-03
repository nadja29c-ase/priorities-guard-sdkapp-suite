# Part A Report — PG Authenticated Data Deletion: Inventory Verification

**Increment:** `inc_pg_authenticated_data_deletion.md` (v1)
**Part:** A — inventory verification, no code
**Date:** 2026-08-03
**Status:** Complete. §3.6 unblocked and completed 2026-08-03 against
`doc/legal/data_retention_strategy.md` (§4 below).

This is the gate artifact. Parts B–F depend on the inventory below being correct.

Everything here is verified from source at the paths cited. Where something could not be
verified, it is listed in §8 rather than assumed.

---

## 1. PG-owned tables

Built independently — from every `__tablename__` in `backend/`, every
`ForeignKey("core_users.id")`, and every `ForeignKey("pg_*")` — then diffed against ADR_008 §1.

| Table | Links to user | `ondelete` | Deletion | ADR_008 §1 |
|---|---|---|---|---|
| `pg_priorities` | direct `user_id` → `core_users.id` | CASCADE | **explicit** | listed |
| `pg_goals` | transitive `priority_id` → `pg_priorities.id` | CASCADE | cascade | listed |
| `pg_deliverables` | transitive `priority_id` → `pg_priorities.id` | CASCADE | cascade | listed |
| `pg_weekly_snapshots` | **both** `priority_id` → `pg_priorities.id` and `user_id` → `core_users.id` | CASCADE (both) | cascade | listed |

**Diff result: no discrepancies.** Four listed, four found. No table the ADR missed; no table
the ADR lists that does not exist.

### 1.1 Cascade vs explicit (§3.4)

Deleting `pg_priorities` alone removes all four rows, because goals, deliverables and snapshots
all cascade from it. Deleting each explicitly is harmless and recommended for clarity, but the
distinction matters for test assertions:

> An assertion that `pg_goals` is empty after deletion passes whether or not the deletion code
> ever names that table. It tests the FK, not the code.

`pg_weekly_snapshots` carries **two** cascading FKs, so it is removed via either parent. It
disappears even if the deletion code never mentions it.

---

## 2. A fifth PG table existed: `pg_weekly_overview`

Created by `p6k7l8m9n0o1_add_pg_weekly_snapshot_tables.py`, dropped in the **upgrade** of
`s9t0u1v2w3x4_cleanup_orphaned_columns.py`. It held `user_id` and a
`uq(user_id, week_start)`.

**Assessment: low residual risk, but the migration's own claim is not self-evident.**

`s9t0u1v2w3x4`'s docstring states the table was *"never written to or read by any service"*.
That is the basis for treating it as benign. However, `git log -S pg_weekly_overview` over
`backend/apps`, `backend/core` and `mcp_server` returns seven service-layer commits — including
`2168822` (Inc 06 snapshot pipeline), `2b3099e` and `847b892` (Inc 07), and `c4bb691`
*"Simplify weekly report to live computation only (defer persistence)"*.

The `c4bb691` subject supports the docstring: persistence was deferred, so the write path was
removed before it mattered. But service code referencing the table did exist across several
commits, so *"never written to by any service"* is an assertion about deploy history that the
repository alone cannot establish.

**Practical position:** the table does not exist at repo head, and the claim is probably true.
If production DB access is restored, check `pg_weekly_overview` for existence and row count
before relying on it. Do not add it to the deletion code.

**The structural point is the durable one and survives regardless:** a table can exist in
production that the ORM has no knowledge of, and nothing in the current test setup would detect
it. This instance is benign; the class is not. See §6.

---

## 3. Shared tables — exact PG-only filters (§3.5)

> **⚠️ CORRECTED 2026-08-03 — this table was incomplete when first published.**
> `oauth_authorization_codes` was **missing** and is added below. Found by adversarial review
> of Part B, not by Part A. That is failure mode 3 from §0.2 — a missed table — occurring in
> the artifact whose whole purpose is to prevent it.
>
> Practical exposure is near zero: codes are single-use, expire in 10 minutes, and are swept
> by `cleanup_expired_oauth_codes`, so a user deleting their data is unlikely to hold a live
> one. The process failure matters more than the row. §3.1 told me to enumerate every table
> with a `user_id` column or an FK chain to `core_users.id`; this table has both, and my own
> FK enumeration in §1 surfaced it (`oauth_provider/models.py:75`). I did not carry it from
> that list into the shared-table analysis. The reference implementation deletes it too — a
> second signal passed over.

| Table | PG-only filter | Verdict |
|---|---|---|
| `core_consents` | `app_name == "priority_guardian"` | **Clean** |
| `oauth_access_tokens` | `'pg.access' = ANY(scope)` (`scope` is `ARRAY(String)`) | **Clean** |
| `oauth_authorization_codes` | `'pg.access' = ANY(scope)` (`scope` is `ARRAY(String)`) | **Clean — added 2026-08-03** |
| `core_connections` (Google) | `user_id` + `provider == "google"` **AND** `connection_type == "google"` | **Constrained — see 3.2** |
| `oauth_sessions` | — | Retain (§4) |
| `core_tool_audit_log` | — | Retain; written, never deleted |

### 3.1 Literals, verified

`backend/core/oauth_provider/authorize.py::APP_PREFIX_MAPPING`:

```python
APP_PREFIX_MAPPING = {
    "clarity.": "mindsort",
    "pg.":      "priority_guardian",
    "focused.": "focused",   # legacy, deprecated
}
```

So PG consent rows carry `app_name="priority_guardian"` and MindSort's carry `"mindsort"`.
`_derive_app_name_from_scopes` in `consent_ui.py` applies the same mapping as a rolling-deploy
fallback and agrees.

PG tokens carry scope `pg.access`; MindSort tokens carry `clarity.write`
(`discovery.py::SCOPES_SUPPORTED`, `mindsort_discovery.py::SCOPES_SUPPORTED_MINDSORT`).

**Edge case, low risk:** `consent_ui.py` records consent under `app_name="unknown"` when no
prefix matches, deliberately preferring an accurate label over omission. A `pg.access` consent
should never reach that branch, since `classify_scopes` rejects multi-app requests and the
`pg.` prefix always maps. A filter on `app_name` alone would miss such a row if one existed.

### 3.2 `core_connections` — the §3.5 blocker condition, qualified

`core_connections` has **no `app_name` column**. The Google row is identified only by `provider`
and `connection_type`. Both PG and Focused query it
(`backend/apps/focused/routers/google_connection_router.py`).

**The filter is PG-only by current product reality — Focused is deprecated and its Render
service suspended — not by schema ownership.** Recorded as a known constraint per §2 (no schema
change in this increment). If Focused is ever revived, PG deletion would take its Google
connection with it.

**Decision for this increment: use the conjunction** — `provider == "google" AND
connection_type == "google"`.

### 3.3 Inconsistent predicates across the codebase — flagged, not fixed

Three different predicates are live for the same row:

| Predicate | Sites |
|---|---|
| `provider` **and** `connection_type` | 6 — `priorities_router`, `calendar_service`, `google_connection_router`, `weekly_report_service`, `snapshot_service` |
| `provider` only | 1 — `offboarding_router.py:84` (`/disconnect`) |
| `connection_type` only | 1 — `reconcile_router.py:147` (fresh-shell check) |

Not fixed here: `/disconnect` and identity code are both out of scope (§2).

---

## 4. §3.6 classification — COMPLETE

Unblocked 2026-08-03 by `doc/legal/data_retention_strategy.md`. Classified against that
document, ADR_008, and code — not against this briefing's assumptions.

| Category | Action | Source | Agreement |
|---|---|---|---|
| PG app tables — `pg_priorities`, `pg_goals`, `pg_deliverables`, `pg_weekly_snapshots` | **Delete** | Retention §3 step 1 (`sdk_app_name_*`); ADR_008 §1 | Agree |
| `core_connections` (Google) | **Revoke at Google, then delete** | Retention §2 + §3 step 2; ADR_008 §1 | Agree — see 4.1 |
| `core_consents` (`app_name="priority_guardian"`) | **Delete** | Retention §2 trigger = user revocation; §3 step 2; ADR_008 §1 | Agree — see 4.2 |
| `oauth_access_tokens` (`'pg.access' = ANY(scope)`) | **Revoke, then delete** | ADR_008 §1 | **CONFLICT — see 4.3** |
| `oauth_authorization_codes` (`'pg.access' = ANY(scope)`) | **Delete** | Reference implementation; same shape as tokens | Added 2026-08-03 — see §3 correction |
| `oauth_sessions` | **Retain** | Retention §7.1 decision; ADR_008 §1 | Resolved |
| `core_tool_audit_log` | **Retain — write, never delete** | ADR_008 §3; Retention §2 (90 days) | Agree |
| `core_users` | **Retain** | ADR_008 §2 | Agree |
| Redis | **No action required** | Retention §3 specifies `redis.delete_pattern(f"{user_id}:*")` | See 4.4 |
| `*_onboarding_state`, `*_scheduled_jobs` | **Not applicable** | Retention §2 lists both suite-generically | PG has neither table (§1) |

### 4.1 `core_connections` — the "(if revoked)" qualifier

Retention §3 step 2 reads *"`core_consents` and `core_connections` (**if revoked**)"*. Two
readings are available: a sequencing statement (revoke, then delete) or a conditional gate
(delete only if revocation succeeded).

Briefing §4 already decides this in the atomicity rules: if Google revocation cannot be
confirmed, **the row is still deleted locally** and the audit entry records the unconfirmed
revocation, because a user's erasure right must not depend on a third party's availability.

**Flagged rather than silently chosen.** The briefing's rule governs; a literal reading of the
source would leave the row in place when Google is unreachable, which is the outcome §4
explicitly rejects.

### 4.2 `core_consents` — the source does resolve it

The briefing asked whether *"retained to prove lawful processing, deleted on user revocation"*
applies when the user requests deletion rather than revocation.

**It does, and the answer is delete.** A request to delete PG data is a withdrawal of consent
for PG processing. The source's stated trigger therefore fires, and §3 step 2 deletes the rows.
ADR_008 §1 independently says delete PG-scoped rows only. Both agree.

**Accountability side-effect, for Part D rather than for the code:** once the consent row is
gone, the only surviving evidence that processing was lawful is the `core_tool_audit_log` entry,
which itself expires at 90 days. After that, no record remains that consent was ever granted.
That is a consequence of honouring erasure, not a defect — but the policy should not imply
otherwise.

### 4.3 `oauth_access_tokens` — a third conflict, not among the two known ones

The briefing asked whether the strategy's 30-day *"token audit log"* is a separate artefact or
these rows. **It is these rows.** Retention §2 locates it precisely:

> | Token audit log | `oauth_access_tokens` **metadata** | 30 days | Traceability and security auditing |

This is **distinct from** the 30-day *verification* log addressed in Retention §7.2. The source
contains two different 30-day figures; §7.2 resolved only one of them.

**The conflict:** ADR_008 §1 says revoke then delete the `pg.access` rows. The source says token
metadata is retained 30 days for traceability and security auditing. Deleting on request
destroys that trail early. The source's §3 sequence never mentions `oauth_access_tokens` at all —
they would vanish by FK CASCADE from `core_users` in Operation B, so the source never
contemplated deleting them *without* deleting the user.

**Reported, not resolved.** Per §3.6 this needs a decision, and it is the same shape as §7.2:
an Operation A question the source could not have answered.

### 4.4 Deleting token rows does not revoke access

Verified independently for PG, not inherited from ADR_006:
`mcp_server/priority_guardian/mcp_auth.py` extracts `jti` from the JWT but **never queries
`oauth_access_tokens`**. Validation is JWKS signature plus claims. There is no revocation lookup
and no database access on the resource-server path.

**Consequence:** deleting the row — or marking it revoked — does not invalidate a live token.
A token already issued stays valid until `exp`. Residual window is
`OAUTH_TOKEN_EXPIRY_SECONDS` (3600) + `TOKEN_EXPIRY_GRACE_SECONDS` (30) = **60m30s** at
defaults, matching ADR_006.

In practice the user's data is already gone, so a surviving token reads an empty account rather
than stale data. But **Part D must not claim that deletion immediately terminates access**, and
Part C's user-facing text should not either.

### 4.5 Decisions carried from the retention document

Recorded there rather than resolved here:

| Item | Decision | Basis |
|---|---|---|
| `oauth_sessions` | **Retain** for PG-scoped deletion | Suite-level browser session. PG-scoped deletion is not account deletion; the strategy's "deleted on account deletion" describes Operation B, which is unimplemented. ADR_008 §1 stands. The apparent conflict dissolves once Operation A and B are distinguished — the strategy predates that split. |
| Audit retention | **90 days** for `core_tool_audit_log` | That is what the code does: `cleanup_expired_audit_logs` runs `WHERE created_at < NOW() - INTERVAL '90 days'`, matching the model comment and ADR_008 §3. The strategy's 30-day figure describes a post-deletion "verification log" — a different artefact, possibly never built. Transcribe both; do not merge. |

The 90-day figure is verified in code. The 30-day figure is **unsupported by any code found in
this repository** — no separate verification-log table or writer exists.

**Part D consequence:** the published privacy policy repeats one of these numbers. Whichever way
the verification-log question resolves, the policy text must match.

---

## 5. Non-SQL and deferred state (§3.7) — all clear

| Surface | Finding |
|---|---|
| **Redis** | **No PG user state.** `offboarding_router.py:48` states it: *"No app-specific Redis cache to clear."* The only PG Redis use is a 10-minute TTL OAuth state token in `google_connection_router` — transient, self-expiring. PG needs no equivalent of Focused's `clear_user_redis_cache`. |
| **Celery** | **No task carries a PG `user_id`.** `renew_google_token(user_id)` and `renew_webhook(user_id, resource_id)` are unimplemented stubs — `pass`, marked TODO, no task decorator, absent from `beat_schedule`. All eight scheduled tasks are sweeps taking no user argument. |
| **Webhooks** | **PG registers none.** No reference to `google_channel_id`, `register_webhook` or `stop_webhook_channel` anywhere in `backend/apps/priority_guardian/`. Only Focused registers them — on the same shared connection row. PG deletion therefore needs no channel teardown. |
| **Cached reports** | None found outside `pg_weekly_snapshots`. |

---

## 6. Schema parity (§3.8) — and the most consequential finding in this report

| Level | Status |
|---|---|
| Repository | `alembic heads` → `b8c9d0e1f2g3`, **single head**, no pending migration |
| Local test DB | **Not alembic-managed** |
| Production | **Unverified and unverifiable under current access** |

### 6.1 The test database is built from the ORM, not from migrations

`tests/conftest.py` builds schema with `Base.metadata.create_all` / `drop_all`. The
`priority_guardian_test` database has no `alembic_version` table and no tables between runs.

**Consequence: the suite structurally cannot catch migration/ORM drift. Tests verify the ORM
against itself.**

For this increment specifically, that undercuts §7's "complete deletion" test. It proves the
code deletes every table *the ORM knows about* — which is precisely the assumption that fails
when production carries a table the ORM does not model. `pg_weekly_overview` is the worked
example.

**Recommendation for Part E:** either build the integration schema by running
`alembic upgrade head` against a scratch database and derive test 3's assertion from
`information_schema.tables` (filtered to `pg_%` plus the shared tables), or state plainly in the
test docstring that the assertion is ORM-derived and cannot detect an unmodelled table.

> **DECISION (Nadja, 2026-08-03): take the migration-built version.** Test 3's schema comes from
> `alembic upgrade head` against a scratch database, and its assertion is derived from
> `information_schema.tables` — not from ORM metadata.
>
> Rationale: the ORM-derived version can only prove *"the code deletes every table the ORM knows
> about"*, which is precisely the assumption `pg_weekly_overview` demonstrates can fail. For a
> test backing a published privacy-policy claim, an assertion that verifies the ORM against
> itself is not worth much. This is the one test where the extra work buys something real, and
> it exercises the migration chain end to end — which nothing currently does.
>
> The ORM-derived fallback remains acceptable **only** if the migration-built version proves
> impractical, and then the docstring must state plainly that the assertion cannot detect an
> unmodelled table. Part E must state which was taken and why.

**This is repo-wide, not PG-specific. Backlog, not this increment.**

### 6.2 Production parity

DB allowlist has been empty since 2026-07-31 and §0.3 keeps Render access read-only. Production
schema parity is **not something this report can assert**. If it matters before deploy, it is a
human step.

---

## 7. Backups (§3.9) — not verifiable from Render's API

`get_postgres` for `priority-guardian-db` (`dpg-d4o3dnumcj7s738u0img-a`, plan `basic_256mb`,
PostgreSQL 16) returns connection, plan, region and maintenance fields only. **No backup or
retention field is exposed.**

The retention strategy states 7 days. That figure lands with §3.6 and carries into Parts D and
F. Not into the deletion code.

---

## 8. Could not verify

1. **Production schema parity** (§6.2) — and `pg_weekly_overview` makes it material rather than
   theoretical.
2. ~~§3.6 classification~~ — **resolved 2026-08-03**; see §4. One item within it remains open
   for decision rather than verification: the `oauth_access_tokens` token-audit-log conflict
   (§4.3).
3. **Backup retention period** — 7 days per the retention document (§5), **unconfirmed against
   Render**, whose API exposes no backup field. Documentation input for Parts D and F only.
4. **Whether `pg_weekly_overview` ever held rows in production** (§2) — needs DB access.
5. **Whether any production `core_connections` row has `provider='google'` with
   `connection_type='unknown'`** (§9.1) — needs DB access.

---

## 9. Adjacent issues — flagged, not fixed

### 9.1 Fresh-shell check: reachable code-level gap, NOT a confirmed live defect

`reconcile_router.py:147` filters the fresh-shell check on `connection_type == "google"` alone,
and that column has `server_default="unknown"`. A Google row with an unset `connection_type`
would be invisible to the check, classifying a real user as a fresh shell and triggering the
silent cross-user remap described at the top of `doc/OPERATIONS_MIGRATIONS.md`.

**Investigated, and no code path at head can produce such a row:**

| Evidence | Finding |
|---|---|
| Backfill | `7a1f4b2e3c9d` ran `UPDATE core_connections SET connection_type='google' WHERE provider='google'` before making the column NOT NULL |
| Write paths | Exactly two construct `CoreConnection`: `google_connection_repo.py:41` sets `provider="google"` **and** `connection_type="google"` together; `client_service.py:100` writes `oauth_provider` rows with NULL `user_id` |
| CHECK constraint | `ck_connection_type_enum` restricts the value domain to `('google','apple','oauth_provider','unknown')` — it does **not** couple `provider` to `connection_type` |

**Classification: reachable code-level defect candidate, pending production verification.** The
column coupling is unenforced, so the defect is real in principle; no current writer can reach
it, and historical rows were backfilled. Residual exposure is limited to rows written by some
historical path no longer in the tree — checkable only with production access.

**Disposition:** record in ADR_007 §7 limitations and in the `OPERATIONS_MIGRATIONS.md` warning
as a known reachable case rather than a hypothetical. Do not fix here — identity code is out of
scope (§2).

### 9.2 Stale documentation

- `PgPriority` docstring claims deletion cascades "checkpoint history". **No such table exists**
  — stale since the `desired_result` → `pg_goals` restructuring.
- `db_models.py` module docstring lists three tables, omitting `PgGoal`.

### 9.3 Briefing accuracy

§4.5's `CoreToolAuditLog` field list is **correct**: `user_id`, `app_name`, `action`,
`result_status`, `details`, `created_at`. It omits only the `id` primary key. `user_id` is
confirmed **not** a ForeignKey, which is what allows audit rows to outlive the user
(ADR_008 §3).

---

## 10. Part A conclusion

The ADR_008 §1 inventory is **correct as written** for PG-owned tables. Three of five shared
tables have clean PG-only filters; `core_connections` is constrained rather than blocked, and
the constraint is recorded.

The §3.6 classification is complete (§4). Every category carries an action and a source.

**Two items remain open, and both need a decision rather than more verification:**

1. **`oauth_access_tokens` (§4.3)** — the source retains token metadata 30 days for
   traceability; ADR_008 deletes it. An Operation A question the source never contemplated.
   **This one gates Part B**, because it determines whether the deletion service deletes those
   rows or only marks them revoked.
2. **The 30-day verification log** (Retention §7.2) — specified, no writer anywhere in the
   repository. Build it as a distinct record type or strike it from the source. Gates Part D,
   not Part B: until resolved the privacy policy must not claim a 30-day verification retention.

**Part B is otherwise unblocked.** Everything else it needs is settled: the table inventory, the
shared-table filters, the delete/revoke/retain classification, and the atomicity architecture in
briefing §4.

No code was written. No schema was changed.
