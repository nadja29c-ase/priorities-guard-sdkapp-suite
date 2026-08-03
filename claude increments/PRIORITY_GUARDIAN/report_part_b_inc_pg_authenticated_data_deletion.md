# Part B Report — Backend Deletion Service and Route

**Increment:** `inc_pg_authenticated_data_deletion.md` (v1)
**Part:** B — backend deletion service and route
**Date:** 2026-08-03
**Status:** Complete, including post-review corrections

---

## 1. What changed

| File | Change |
|---|---|
| `backend/apps/priority_guardian/services/offboarding_service.py` | **New.** `delete_user_data()`, `revoke_google_access()`, `PgDeletionError` |
| `backend/apps/priority_guardian/routers/offboarding_router.py` | New `POST /delete-data`; `/disconnect` now calls the extracted helper |
| `tests/integration/priority_guardian/test_pg_delete_data.py` | **New.** 11 tests |
| `tests/integration/priority_guardian/test_pg_offboarding.py` | Patch targets repointed; `connection_type` added to fixtures |
| `tests/unit/priority_guardian/test_offboarding_router.py` | Patch targets repointed |
| `tests/E2E_tests/focused/test_offboarding_e2e.py` | `connection_type` added to fixtures |

PG has no `logic/` package — it uses `services/`. The service lives there rather than
importing Focused's layout.

---

## 2. Atomicity evidence (§4)

### 2.1 The transaction boundary, quoted rather than characterised

The whole design rests on `backend/core/database.py::get_db`. Verbatim:

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

So the **request is the transaction**: the session commits when the handler returns and
rolls back if it raises. `delete_user_data()` therefore performs **no commit at all**, and
every local deletion plus the audit entry lands atomically.

This is also the concrete reason `/disconnect` cannot be step 1, as §4 states:
`offboarding_router.py:145` calls `await session.commit()` and the route returns early at
line 97 when the user is already disconnected. Calling it would close the transaction
mid-flow and skip the rest for an already-disconnected user.

### 2.2 Google revocation sits outside the transaction

It is an HTTP call (`revoke_google_token`) performed **before** any DB statement, and its
failure is recorded rather than raised. A user's erasure right must not depend on a third
party being reachable.

The result never collapses the two outcomes:

```python
"success": True,                          # local deletion
"google_revocation_confirmed": google_revoked,   # external
"google_revocation_error": revocation["error"],
```

### 2.3 The reverse case — Google revoked, local rolled back

`delete_user_data` calls `await session.rollback()` explicitly before raising
`PgDeletionError`. `get_db` would also roll back, but doing it in the service makes the
guarantee local to the function rather than dependent on caller plumbing.

The route maps it to **503** with `retryable: true` and `google_revocation_confirmed`, so it
is never reported as "nothing changed" when Calendar access is already gone.

**The failed attempt is recorded as a log event, not a row** (`pg_offboarding.delete_data_failed`,
ERROR). The audit row rolls back with everything else, so a DB record of the failure is not
available by construction. Worth knowing when looking for evidence of a failed attempt.

### 2.4 Retry tolerance

`revoke_google_access` tolerates an absent connection, an absent refresh token, an absent
HTTP client, a non-success response, and a raised exception. That is what makes
`retryable=True` a real guarantee rather than a claim — verified by test, both failure
shapes parametrized.

---

## 3. `/disconnect` — no behaviour change (§2)

The revocation logic was extracted into `revoke_google_access()`; both paths call it. Same
lookup, same filter, same log event names (`pg_offboarding.no_google_connection`,
`no_refresh_token`, `no_http_client`, `google_revoke_failed`, `google_revoke_error`), same
best-effort semantics, same `details` key.

**Proof: its 24 existing tests pass with every assertion untouched.** The only edit was two
patch-target strings moving to the new module — 17 occurrences in `test_pg_offboarding.py`,
8 in `test_offboarding_router.py`. Both files were baselined at green (17 and 7) *before* the
change, so the 5 failures that appeared were attributable rather than lost in the repo's
pre-existing red.

Had an assertion been loosened to get green, the proof would have been destroyed.

---

## 4. Per-test: the bug that would still pass it

All 11 in `test_pg_delete_data.py` carry this in their docstring. Summary:

| Test | Bug it catches |
|---|---|
| `core_users_row_survives` | Deleting the shared anchor — failure mode 1, irreversible |
| `mindsort_data_is_untouched` | Filtering shared tables by `user_id` alone — failure mode 2 |
| `every_pg_table_is_emptied` | A missed table — failure mode 3 |
| `audit_entry_written_and_survives` | Audit never written, deleted, or leaking content |
| `local_failure_rolls_back_every_deletion` | The best-effort sequence §4 forbids |
| `retry_succeeds_after_google_already_disconnected` | A revocation step that treats an already-revoked grant as fatal |
| `google_failure_does_not_block_deletion` | Treating Google as a precondition for erasure |
| `tokens_are_revoked_before_deletion` | `user_id`-only token filter |
| `is_idempotent` | Second call erroring or reporting the first call's counts |
| `user_with_no_data_succeeds` | Assuming a connection or priorities exist |

### 4.1 Mutation results — 10 mutations, all caught

Source restored byte-identically after each; verified by comparison, not assumed.

| # | Mutation | Caught by |
|---|---|---|
| M1 | Delete the `core_users` row | `core_users_row_survives` |
| M2 | `core_consents` filtered by `user_id` alone | `mindsort_data_is_untouched` |
| M3 | `oauth_access_tokens` filtered by `user_id` alone | isolation + token test |
| M4 | Skip the `pg_weekly_snapshots` delete | `every_pg_table_is_emptied` |
| M5 | Never write the audit entry | `audit_entry_written_and_survives` |
| M6 | Swallow the failure, report success | `local_failure_rolls_back_every_deletion` |
| M7 | Already-revoked Google grant treated as fatal | retry test |
| M8 | Block deletion when revocation unconfirmed | `google_failure_does_not_block_deletion` |
| M9 | Drop the `oauth_authorization_codes` delete | `every_pg_table_is_emptied` |
| M10 | Authorization codes filtered by `user_id` alone | `mindsort_data_is_untouched` |

### 4.2 Two of my own tests were vacuous on the first pass

Both found by the harness, not by inspection.

**Emptiness assertions proved nothing about the code.** Every child table cascades from
`pg_priorities`, so removing the explicit `pg_weekly_snapshots` delete left the test green —
M4 survived. This is the exact trap recorded in **Part A §1.1**, written by me and then walked
into. Fixed by also asserting the reported row counts: emptiness tests the foreign key,
counts test the code. Both are kept.

**The retry test exercised only one failure shape.** It mocked Google *returning* a
non-success response, never *raising*, so M7 — re-raising inside the `except` branch —
survived: that branch was never entered. Now parametrized over both, since an already-revoked
grant can surface either way and they take different paths through `revoke_google_access`.

---

## 5. Post-review corrections

Adversarial review of this part produced two findings; both accepted.

### 5.1 `oauth_authorization_codes` was missing — and it traces to Part A

The table has a `user_id` FK to `core_users.id` and a `scope` ARRAY: the same shape as
`oauth_access_tokens`, with the same clean filter. The reference implementation deletes it.
Part B did not, because **Part A's shared-table inventory omitted it**.

That is failure mode 3 occurring inside the artifact designed to prevent it. Exposure is near
zero — codes are single-use, expire in 10 minutes, and `cleanup_expired_oauth_codes` sweeps
them — but "verified inventory" has to mean verified.

Now deleted, scope-filtered, covered by M9/M10, and **Part A §3 and §4 corrected** with a
note recording that Part A missed it rather than silently adding the row.

### 5.2 The revoke-then-delete rationale was overstated

The comment claimed the `revoked` flag is what makes a concurrent refresh fail cleanly. It
isn't: inside one transaction the UPDATE is invisible to other sessions until commit, by
which point the DELETE is visible too — a concurrent refresh blocks on the row lock and then
finds the row gone. The flag adds nothing the delete does not already provide.

Reworded to "belt and braces, matching Focused," with the reasoning recorded so a future
reader does not rely on a protection the transaction semantics don't give.

---

## 6. Fixtures corrected repo-wide

Google `CoreConnection` fixtures were being created **without** `connection_type`, landing as
`'unknown'` via the column's server default — a row shape **no production write path
creates** (Part A §9.1: both writers set the columns together, and `7a1f4b2e3c9d` backfilled
existing rows).

Tests were therefore exercising impossible data, with two consequences: any test of the
conjunction filter ran against rows that cannot occur, and a `provider`-only filter would pass
while conjunction-filtered production code would miss those rows entirely.

Fixed at all 6 sites in the 2 tracked files that omitted it
(`test_pg_offboarding.py` ×2, `test_offboarding_e2e.py` ×4). Eight other files already set it.

**No CHECK constraint added.** Coupling the columns at schema level is a migration, out of
scope, and would fire the `OPERATIONS_MIGRATIONS.md` fresh-shell warning for no benefit.
Filed as backlog if the invariant is wanted in the schema.

*Untouched: `tests/unit/apps/__pycache__/focused/test_offboarding.py` — a stray `.py` inside
`__pycache__`, untracked by git.*

---

## 7. Suite delta

| | Baseline | With Part B |
|---|---|---|
| failed | 321 | 321 |
| errors | 14 | 14 |
| passed | 3151 | 3162 |

**Zero regressions.** The +11 is exactly the new tests. Both runs used `--maxfail=2000`; note
the repo's pytest config sets `maxfail=5`, which silently truncates an uncapped run and made
the first comparison meaningless until it was pinned.

**Baseline document is badly stale.** `doc/testing_baseline_2026-07-04.md` records 5
documented / 34 actual. The suite is at **321 failed / 14 errors**. The 34 appears to have
been measured on a subset — the MindSort and OAuth directories alone give 35. Flagged, not
addressed: out of scope here.

---

## 8. Not verified / assumed

1. **Nothing is deployed.** Backend is `autoDeploy: no`; this commit ships nothing.
2. **No production database access**, so the deletion has never run against real data. The
   integration tests run on the local ORM-built schema — with the §6.1 limitation from Part A
   still standing: it cannot detect an unmodelled table.
3. **Latency at realistic maximum volume (§10) not yet measured.** Deferred to Part C, where
   the MCP tool's `TIMEOUT_S = 8.0` makes it actionable.
4. **`data_retention_strategy.md` §7.3 had not landed** when this was implemented. The
   `oauth_access_tokens` decision (revoke, then delete, same transaction) was implemented from
   Nadja's instruction directly, not from the document.

---

## 9. Adjacent issues — flagged, not fixed

1. Three divergent `core_connections` predicates remain live across eight sites (Part A §3.3).
   Unchanged: `/disconnect` and identity code are out of scope.
2. `oauth_authorization_codes` is deleted by Focused inside `disconnect_user`, not
   `delete_user_data`. PG places it in deletion, which is the correct scope for PG; the
   asymmetry between apps is noted, not reconciled.
3. The repo's `maxfail=5` pytest default makes any uncapped full-suite run misleading.

---

## 10. Definition of done

Part B is complete. **Part C is not blocked** by anything here.

The `oauth_access_tokens` retention conflict (Part A §4.3) is **resolved and implemented** —
revoke then delete. The remaining open item is the 30-day verification log, which gates
Part D, not Part C.
