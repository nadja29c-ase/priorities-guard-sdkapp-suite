# Part A Report — PG Authenticated Data Deletion: Inventory Verification

**Increment:** `inc_pg_authenticated_data_deletion.md` (v1)
**Part:** A — inventory verification, no code
**Date:** 2026-08-03
**Status:** Complete except §3.6, which is blocked on `doc/legal/data_retention_strategy.md`

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

| Table | PG-only filter | Verdict |
|---|---|---|
| `core_consents` | `app_name == "priority_guardian"` | **Clean** |
| `oauth_access_tokens` | `'pg.access' = ANY(scope)` (`scope` is `ARRAY(String)`) | **Clean** |
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

## 4. §3.6 classification — BLOCKED

Not attempted. `doc/legal/data_retention_strategy.md` does not yet exist; the source PDF lives
in project knowledge and is not reachable from the repository.

Two decisions have been taken in advance and should be recorded in that document rather than
resolved by this report:

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
2. **§3.6 classification** in full — pending `doc/legal/data_retention_strategy.md`.
3. **Backup retention period** — not exposed by Render's API; doc is the source.
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

**Nothing blocks Part B on the inventory itself.** The two open dependencies are §3.6 (awaiting
the retention document) and the Part E test-derivation question raised in §6.1.

No code was written. No schema was changed.
