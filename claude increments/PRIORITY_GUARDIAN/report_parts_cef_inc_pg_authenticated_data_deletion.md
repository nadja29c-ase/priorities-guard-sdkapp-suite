# Parts C, E, F Report — PG Authenticated Data Deletion

**Increment:** `inc_pg_authenticated_data_deletion.md` (v1)
**Parts:** C (MCP tool), E (tests), F (erasure runbook) + the §11 pre-deploy gate
**Date:** 2026-08-03
**Status:** C, E, F complete. D blocked on a decision that is not mine.

Parts A and B have their own reports:
`report_part_a_…md`, `report_part_b_…md`. Atomicity evidence lives in Part B §2 and is not
repeated here.

---

## 1. Commit SHAs (§12.1)

| SHA | Part | What |
|---|---|---|
| `006a556` | A | Inventory gate artifact |
| `4e4e057` | — | Briefing updated to the version A was executed against |
| `9174742` | A | Part E test-3 decision recorded |
| `dbb8079` | A | §3.6 classification + retention transcription |
| `cd47ad0` | B | Deletion service + route |
| `828319f` | B | Review fixes: missed table, rationale, fixtures |
| `6327436` | — | Orphaned Focused tests rescued (standalone, not this increment) |
| `a871333` | C | MCP tool + bounded Google revocation |
| `5393ff8` | E | Migration-derived coverage (skipping — see §6) |
| `a2235da` | F | Erasure runbook |
| `70537e0` | E | Three §7 gaps closed after self-audit |

All pushed. `main` == `origin/main`.

---

## 2. Part C — what changed and which requirement it satisfies (§12.3)

| File | Change | Requirement |
|---|---|---|
| `tools/delete_my_priority_guardian_data.py` | New tool | §5 |
| `tools/__init__.py` | Registered in the shared `TOOL_REGISTRY` | §5 "both PG servers" |
| `services/offboarding_service.py` | `GOOGLE_REVOCATION_TIMEOUT_S`, `timeout_s` param | §10 latency |

**Naming (§5, ADR_008 §4).** `delete_my_priority_guardian_data`, titled "Delete My Priority
Guardian Data". Never "account".

**Description states all four required things:** what it deletes; that other Priority Guard
apps are unaffected with MindSort named explicitly; that it cannot be undone; when to call
and when not to — including that a whole-account request routes to support rather than being
over-served by this tool.

**Annotations, verified in the SERVED `tools/list` payload on both platforms:**

| | title | readOnlyHint | destructiveHint | openWorldHint |
|---|---|---|---|---|
| Claude | ✓ | False | **True** | True |
| ChatGPT | ✓ | False | **True** | True |

Set in the shared `ToolDefinition`. **No `_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES` entry** —
verified absent programmatically, not by eye.

**`openWorldHint` corrected from the briefing.** §5 originally mandated `False`. Implemented
as `False` first because briefing constraints bind (RULE 0a), flagged rather than overridden,
and corrected by Nadja: the tool does reach an external system, and every other PG tool that
does sets `True`. Briefing §5 now carries the correction inline.

**Result text describes categories, never schema (§5).** Table names, row counts and
`audit_log_id` stay in `structuredContent`. The 503 retryable path has its own text that never
says "nothing happened" when Calendar access is already gone.

---

## 3. The Part C finding — an unbounded external call inside an irreversible operation

`backend/main.py:105` builds the shared client as `httpx.AsyncClient(timeout=30.0)`, and
`revoke_google_token` passes no timeout of its own. The MCP tool budget is `TIMEOUT_S = 8.0`.

Unbounded, a slow Google produces the worst outcome available here: **the tool times out and
tells the user their data was NOT deleted, while the backend request keeps running, completes
revocation, deletes everything and commits.** The user is told nothing happened when
everything did — on an operation that cannot be undone.

Bounded at `GOOGLE_REVOCATION_TIMEOUT_S = 3.0`, applied to the **deletion path only** via a
`timeout_s` parameter defaulting to `None`. `/disconnect` is out of scope (§2) and keeps its
existing unbounded behaviour, asserted by a test. A revocation timeout is reported as
unconfirmed and deletion proceeds, which costs nothing because revocation was already
best-effort.

---

## 4. §10 latency and the bounding decision (§12.7)

Measured at realistic-plus-headroom volume: 3 priorities, 600 weekly snapshots (~4 years),
9 goals, 9 deliverables, 1 Google connection — 621 rows.

```
total=0.53s   google=0.50s   local=0.03s   budget=8.0s
```

**Bounding decision (§10): no batching or limit is required, and none was added.** PG caps at
3 active priorities and snapshots are one per priority per week, so even a heavy multi-year
user lands in the hundreds of rows. 621 rows delete in 30ms — three orders of magnitude inside
the budget. The external call is **94%** of the total, which is why volume was never the risk
and the unbounded client was.

**The first version of this measurement was vacuous.** The seeded user had no
`CoreConnection`, so `revoke_google_access` returned early at `connection is None`, the mocked
latency never ran, and it reported `local=-0.49s`. It now asserts `core_connections == 1`, so
it fails if the Google call is skipped rather than silently timing only the deletes.

---

## 5. Part E — tests (§12.4)

**33 tests across three files.** Every test states the bug that would still pass it.

| File | Tests | Level |
|---|---|---|
| `integration/…/test_pg_delete_data.py` | 14 | Real database |
| `unit/…/test_pg_delete_data_unit.py` | 8 | Mocked session — statement inspection |
| `integration/…/test_pg_delete_data_schema_coverage.py` | 3 | Migration-built schema (**skipping**, §6) |

### 5.1 Mutation results — 14 mutations, all caught

Source restored byte-identically after each, verified by comparison.

| # | Mutation | Caught by |
|---|---|---|
| M1 | Delete the `core_users` row | `core_users_row_survives` |
| M2 | `core_consents` by `user_id` alone | `mindsort_data_is_untouched` |
| M3 | `oauth_access_tokens` by `user_id` alone | isolation + token test |
| M4 | Skip the `pg_weekly_snapshots` delete | `every_pg_table_is_emptied` |
| M5 | Never write the audit entry | `audit_entry_written_and_survives` |
| M6 | Swallow the failure, report success | `local_failure_rolls_back_every_deletion` |
| M7 | Already-revoked grant treated as fatal | retry test |
| M8 | Block deletion when revocation unconfirmed | `google_failure_does_not_block_deletion` |
| M9 | Drop the `oauth_authorization_codes` delete | `every_pg_table_is_emptied` |
| M10 | Authorization codes by `user_id` alone | `mindsort_data_is_untouched` |
| U1 | `core_consents` by `user_id` alone (unit) | `shared_tables_are_filtered_by_scope` |
| U2 | Drop a child delete a cascade would hide | `targets_exactly_the_expected_tables` |
| U3 | Add a DELETE against `core_users` | `never_targets_the_protected_tables` |
| U4 | Commit inside the service | `never_commits` |

### 5.2 Five vacuous constructions, all caught — and the pattern

| # | Where | How it surfaced |
|---|---|---|
| 1 | Emptiness assertions satisfied by the FK, not the code | M4 survived |
| 2 | Retry test exercised only the return-failure path | M7 survived |
| 3 | Latency test measured nothing (no connection seeded) | `local=-0.49s` |
| 4 | Unit-test mocks: `decrypt_token` failed, so `revoke_google_token` was never called in any of 8 tests | `google_revoked` was False |
| 5 | Derived assertion against an empty `Base.metadata` | Caught pre-emptively by an added non-empty guard |

**The pattern is consistent and worth carrying forward: it is always the mock or the fixture,
never the assertion.** The assertion reads correctly; the setup means it never reaches the
code under test.

**Every one of these was caught by an assertion that checked a VALUE rather than an
ABSENCE** — `google_revoked is True`, non-empty metadata, negative elapsed time.
Absence-based assertions ("no rows remain", "no error raised") are precisely the ones that
pass when nothing ran. **Prefer assertions that fail on an unexecuted path.**

---

## 6. Task #9's effect on Part E — stated here rather than footnoted

**The strongest test backing a privacy-policy claim runs in its weaker form.**

Part A §6.1 recorded Nadja's decision to derive the "complete deletion" assertion from a
**migration-built** schema rather than from ORM metadata, because the ORM cannot detect a
table it does not model — the `pg_weekly_overview` class of problem.

That test is implemented (`test_pg_delete_data_schema_coverage.py`) and **it skips**, because
`alembic upgrade head` fails on a fresh database:

```
ALTER TYPE job_type_enum ADD VALUE IF NOT EXISTS 'activation'
UndefinedObject: type "job_type_enum" does not exist
```

Root cause (task #9): `env.py` runs the whole chain in one transaction with no
`transaction_per_migration=True`, while `h8c9d0e1f2g3` opens a separate AUTOCOMMIT connection
that cannot see the still-uncommitted `CREATE TYPE` from `e5f6a7b8c9d0`. Production is
unaffected — it was built incrementally, so the type was committed before that connection
opened.

**What this costs the increment:** the running assertion is derived from `Base.metadata`,
which catches a new `pg_*` model added without a matching delete, but **cannot** catch a table
present in production and absent from the ORM. That limitation is stated in the test docstring
rather than left implicit, which is what §6.1 permits when the migration-built form is
impractical — and it is impractical for a reason external to this increment.

**When task #9 is fixed, re-run this test rather than leaving it skipping.**

---

## 7. Part F — erasure runbook

`doc/OPERATIONS_ERASURE.md`. Every §8 bullet:

- Operation A: direct the user to the in-app tool — stated as *the* answer
- Operation B: **not specified**, with the required paragraph verbatim; no procedure invented
- Identification per ADR_008 §5, case-by-case, and it explicitly **forbids** asking a
  requester to confirm priority names or keywords, with the reason
- The 30-day clock, and that six-month inactivity cleanup is not request fulfilment
- What is retained and why

Two accuracy points added because support would otherwise state them wrongly: backups are not
reached (7-day expiry), and access does not stop at the same instant (JWKS-only validation, up
to 60m30s — ADR_006, re-verified for PG in Part A §4.4).

---

## 8. §11 pre-deploy gate

**`OPERATIONS_PREDEPLOY.md` read in full (419 lines).** Applicable items executed:

| Item | Result |
|---|---|
| Single alembic head | ✓ `b8c9d0e1f2g3`, exactly 1 |
| Stash before overwrite | ✓ used before every baseline stash/pop |
| Stage specific files, never `git add -A` | ✓ explicit paths on every commit |
| Poetry lock consistency | N/A — `pyproject.toml` / `poetry.lock` untouched |
| Widget bundle checks | N/A — no widget files touched |
| OAuth discovery sanity check | N/A — no OAuth or discovery code changed |
| Production schema diff | Not possible — allow list empty by design since 2026-07-30 |

**Fresh-shell warning — stated explicitly as §11 requires: it does NOT fire.** This increment
adds **no table**; `git diff` over `backend/alembic/` across the whole increment is empty. The
`OPERATIONS_MIGRATIONS.md` warning applies to migrations adding PG-owned state tables, and
`_reconcile_user_by_subject`'s fresh-shell check therefore needs no extension.

**`WIDGET_VERSION` — no bump required.** It lives in `handlers/resources.py:108` and governs
the widget bundle. The deletion tool has `widget_uri=None` and no widget files changed.

> Minor: the documented check `grep -rn "WIDGET_URI = "` expects exactly one match. It now
> returns four, because three tools (`inspect_adapt`, `get_patterns`, and this new one)
> declare a local `WIDGET_URI = None`. Pre-existing looseness in the check's grep, not a
> second source of truth — `constants.py:17` remains the only real URI. Flagged, not changed.

### 8.1 Two stale entries noticed in that document

Flagged, not fixed:

- **Line 385** documents `CLARITY_CLAUDE_AUDIENCE = https://www.priority-guard.com` (the
  issuer). That is the value §11 of the *previous* increment corrected: production now holds
  the resource URL, and MindSort-Claude's boot guard hard-fails if it drifts back.
- **Line 301** describes the PG Claude MCP server as "currently deprecated". It is awaiting
  resubmission, and this increment ships a tool to it.

---

## 9. Suite delta (§11) — the literal comparison, with the caveat

`doc/testing_baseline_2026-07-04.md` records:

> **Total tests:** ~2292 — **Status:** ~154 known-red in included suite, 5 excluded behind
> `mcp_focused` collection ignore

Measured 2026-08-03 with `--maxfail=0`:

| | Baseline doc (2026-07-04) | Now |
|---|---|---|
| Total | ~2292 | ~3523 |
| Known-red | ~154 | **321** (+ 14 errors) |

**The document is describing a different universe, and the honest number is the delta, not the
absolute.** Before and after every change in this increment: **321 failed / 14 errors,
unchanged.** Passed rose 3151 → 3186, accounted for entirely by tests this increment added.

**Correction to the briefing's own framing.** §11 says the baseline is "known stale (5
documented vs 34 actual)". The document actually documents **~154** known-red; the "5" is the
count of suites excluded behind a collection ignore. Both figures in that parenthetical are
wrong, which is itself the stale-artifact pattern this increment kept finding.

**And every bare `pytest` run in this repo reports a truncated number** — the config sets
`maxfail=5`. Same tree, same commit: bare → 5, `--maxfail=200` → 186, uncapped → 321. Filed as
task #8. Any suite figure cited as evidence must pass `--maxfail=0`.

---

## 10. Could not verify / assumed (§12.9)

1. **Production schema parity — unverified and unverifiable** under current access (empty
   allow list, read-only Render). `pg_weekly_overview` makes it material rather than
   theoretical.
2. **Nothing is deployed.** The deletion has never run against production data.
3. **Host confirmation behaviour on either platform.** Split as agreed: annotations verified
   correct and correctly served; observing that ChatGPT and Claude actually render the
   confirmation requires a deploy and Nadja's accounts.
4. **Backup retention (7 days)** comes from the retention document. Render's API exposes no
   backup field for `priority-guardian-db`.
5. **Migration-built schema coverage** — see §6.
6. **The 30-day verification log** has no writer anywhere in the repository. Gates Part D.

---

## 11. Adjacent issues — flagged, not fixed (§12.10)

| # | Issue | Filed |
|---|---|---|
| 1 | `pytest maxfail=5` truncates every uncapped run | task #8 |
| 2 | `alembic upgrade head` fails from base | task #9 |
| 3 | Test DB built by `create_all`, not migrations — cannot catch drift | Part A §6.1 |
| 4 | Three divergent `core_connections` predicates across 8 sites | Part A §3.3 |
| 5 | Fresh-shell gap: reachable code-level candidate, unreachable at head | Part A §9.1 |
| 6 | `OPERATIONS_PREDEPLOY.md` stale entries (§8.1) | this report |
| 7 | PG-OpenAI's weaker `_prod_url_invariants` predicate | task #5 |

---

## 12. Deployment status (§12.11)

**Nothing deployed. Nothing would deploy on push.**

| Service | autoDeploy | Affected by this increment |
|---|---|---|
| `priorities-guard-sdkapp-shared-backend` | **no** | Yes — service + route |
| `priorities-guard-pg-mcp` (PG-OpenAI) | **no** | Yes — new tool |
| `priority-guardian-claude-mcp` (PG-Claude) | **no** | Yes — new tool |
| `priorities-guard-mindsort-claude-mcp` | **yes** | **No** — untouched |

The only auto-deploying active service is MindSort-Claude, and nothing here goes near it. All
three services this increment touches require a manual deploy, which matches §0.3 and answers
the "check before committing" question: **no branch was needed.**

Deploy order when it happens: **backend first** (the tool calls a route that must exist), then
the MCP servers.

---

## 13. Definition of done

| § | Requirement | Status |
|---|---|---|
| 12.1 | Commit SHAs | §1 |
| 12.2 | Part A inventory, diff, filters, classification, conflicts | Part A report |
| 12.3 | Per part: what changed, where, which requirement | §2, §5, §7 |
| 12.4 | Per test: bug caught + mutation results | §5 |
| 12.5 | Atomicity evidence | Part B report §2 |
| 12.6 | Confirmation on both platforms | **Half done by design** — §2, §10.3 |
| 12.7 | Timeout measurement at realistic volume | §4 |
| 12.8 | Backup retention period | 7 days — §10.4 |
| 12.9 | Could not verify / assumed | §10 |
| 12.10 | Adjacent issues | §11 |
| 12.11 | Deployment status | §12 |

**Parts C, E and F are complete. Part D is blocked** on striking the 30-day verification log
from the retention strategy — a change to a signed artefact, and not a decision an
implementing increment should make.
