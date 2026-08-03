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

> **This section predates the adversarial reviews. See §14 onward, added 2026-08-03 after
> three Codex passes produced fourteen findings — two of which would have shipped broken.**


---

## 14. Adversarial review — two rounds, six passes (added 2026-08-03)

Run after Parts A–F were reported complete. Split into three focused passes because the
increment spans ten commits; one review would have skimmed everything.

| Pass | Target | Real findings | Fixed now | Deferred |
|---|---|---|---|---|
| 1 | `offboarding_service.py` | 5 | rollback guard | 3 documented-unreachable, 1 already recorded |
| 2 | tool + route + `http_client` + dispatchers | 5 | idempotency message, false comment | security (#10), `widget_accessible`, Claude adapter |
| 3 | the four test files | 4 | all 4 | 2 recorded |

Commits: `93987f5`, `ad30272`, `9713b94`.

### 14.1 The two that would have shipped broken

**The 503 seam.** `backend_post` returns the parsed body for 4xx but RAISES for 5xx. The
route signalled its retryable case with 503, so the tool's entire error branch was
unreachable and the user got the dispatcher's generic "Something went wrong" — in exactly the
scenario the atomicity design exists for, with no hint their Calendar access was already
gone. Found before the reviews; the reviews then found that **nothing tested the router's
side of that contract either**, so changing 503→500 would have broken production with every
test green.

**The conjunction filter had no test at all.** Every fixture set both `provider` and
`connection_type`, so `provider == "google"` alone matched every row. Dropping
`connection_type` survived the **entire suite** — 23 passed, zero failures. That is the
filter Part A deliberated and Nadja ruled on; a provider-only implementation would have
shipped green, silently reversing the decision toward cross-app destruction.

Both share a shape: **a decision correctly made, correctly documented, and never verified.**

### 14.2 Deferred with reasons

- **#10 (security, ChatGPT only)** — client-controlled `_meta["openai/subject"]` can redirect
  the effective user through reconciliation case C1. Verified from source. Predates this
  increment; this increment attaches an irreversible verb to it. PG-Claude never reconciles
  and is unaffected. Recommended mitigation: skip reconciliation for `destructive_hint=True`
  tools and use the JWT `sub`, which fails safe.
- **Three unreachable filter defeats** — documented at the constant block in the service with
  the *direction* of each fix, because two point opposite ways (widen the consent filter,
  narrow the token filter, do not touch the connection conjunction).
- **`widget_accessible=False` not enforced** — discovery metadata only, in both dispatchers.
  A dispatcher change touching every tool; its own increment.

### 14.3 A SECOND round, re-derived rather than anchored

The first three passes were re-run at `b570afc`. The first attempt at round 2 told Codex what
round 1 had found and asked it to verify the fixes. **That was wrong and Nadja stopped it.**
An anchored review confirms what you already suspect; it cannot find what you did not think
to ask about. The passes were cancelled and relaunched with no prior findings, plus one
instruction round 1 did not have: *ignore the comments' claims — treat every documented
guarantee as a hypothesis to disprove.* That instruction mattered because the code had since
accumulated confident documentation, including three "unreachable" claims written by me.

The unanchored passes found three classes the anchored ones structurally could not:

| Finding | Severity |
|---|---|
| **Cross-user isolation had NO test.** A service deleting EVERY user's data passed 33/33 | **critical** |
| `asyncio.CancelledError` bypassed rollback, the error event and `PgDeletionError` — it is a `BaseException`, and both this service and `get_db` guard on `except Exception` | high |
| Part A's "Redis: none" was wrong in scope — `oauth:auth:<id>` carries `user_id` | medium |
| Four user-facing statements false in reachable states, two written that same day | high |

The tool pass also **independently re-derived the #10 identity finding** without being told
it existed, which is the strongest available confirmation that it is real.

Commits: `bcbed49`, `8b4d166`.

### 14.4 Confirmed safe

Codex returned no defect on the two vectors most expected to fail: the
`pg_goals`/`pg_deliverables` subquery does evaluate before the parent delete, and the Google
revocation bound genuinely leaves `/disconnect` unchanged.

---

## 15. Four observations that outlive this increment

These are the durable output. The findings themselves are fixed; these are not about this
increment.

### 15.1 The seam has no owner

**Most defects lived at boundaries.** Integration tests call services directly, unit tests
mock sessions, routers are asserted alone. Every layer was verified and every boundary
between layers was assumed.

A statement about the repo's test taxonomy, not about this increment: no category of test has
the contract between two components as its job, so contracts are the one thing nothing checks.
The 503 seam, the unbound router status, and the unasserted POST endpoint were all instances.

### 15.2 It was never the assertion, always the setup

Every vacuous construction was a mock that short-circuited, a fixture that could not express
the discriminating case, or a seam nobody tested. **The assertions read correctly
throughout** — what failed was that they never reached the code under test.

| # | Construction | How it surfaced |
|---|---|---|
| 1 | Emptiness satisfied by an FK cascade, not by the code | mutation survived |
| 2 | Retry test exercised only the return-failure path | mutation survived |
| 3 | Latency test seeded no connection, so the mock never ran | **negative** elapsed time |
| 4 | `decrypt_token` failed on a MagicMock, so the patched revoke was never called in 8 tests | `google_revoked` was False |
| 5 | Derived assertion against an empty `Base.metadata` | caught by an added non-empty guard |
| 6 | **No fixture ever seeded a second user** | deleting every user's data passed 33/33 |

**Assertions that check a VALUE catch these; assertions that check an ABSENCE do not.**
`google_revoked is True`, non-empty metadata, negative elapsed time — each failed loudly.
`assert rows == 0` and "no error raised" are exactly the shapes that pass when nothing ran.
**Prefer assertions that fail on an unexecuted path.**

**The strongest form is #6.** The setup does not merely decide whether a test can fail — it
decides **which mutations are conceivable**. Every mutation run for two days was cross-*app*,
because that was the only axis the fixtures made visible. The work was thorough inside a
space the data had silently defined, and blind to everything outside it.

**Corollary — every user-facing claim has a second surface.** The retryable text was fixed
while `ASSISTANT_GUIDANCE_RETRYABLE` — the string the model reads and relays — still carried
the same false claim. It nearly stayed hidden: a `grep` hit of 2 looked like the new comments
quoting the old text, which was true for two phrases and false for the third. Stripping
comments and re-checking the parsed module found it. **The fix was correct and incomplete,
because only the channel being thought about was checked.** Nothing in this increment treated
model-facing guidance as a surface for user-facing claims until that point.

### 15.3 Every layer of verification failed the same way as the code

Mock, fixture, seam — and then the mutation harness itself.

A cancellation mutation reported **SURVIVED**. It had never applied: the slice matched an
`except Exception as e:` in a *different function*. **A broken mutation and a surviving
mutation produce identical output.** Every "mutation caught" claim in this increment rested
on the unstated assumption that mutations applied.

This is the worst of the four because it is the verification of the verification. The harness
now asserts the target is genuinely absent and that the file shrank before trusting a verdict
— and that guard should be permanent, not a one-off.

### 15.4 The app-directory boundary is not the data boundary

Twice, identically:

| Missed | Where it actually lived |
|---|---|
| `oauth_authorization_codes` | `backend/core/oauth_provider/models.py` |
| Redis `oauth:auth:<id>` carrying `user_id` | `backend/core/oauth_provider/services/authorization_service.py` |

Both times the search stopped at `backend/apps/priority_guardian/` and both times the state
lived in the shared OAuth layer, written on the app's behalf. Part A's inventory strategy
assumed an app owns its data wherever it lives; shared infrastructure breaks that assumption
silently, because nothing in the app directory references what it writes.

Same shape as 15.1 — a boundary nobody owns — but between an application and the
infrastructure it writes through, rather than between two components.

---

## 16. Corrected status and the remaining path

**Five of six parts complete.** Part D is not started and is blocked on one line.

| Part | State |
|---|---|
| A, B, C, E, F | Complete, reviewed, pushed |
| D | **Blocked** — strike the 30-day verification log from `data_retention_strategy.md` |

### 16.1 Decision recorded: tool descriptions are not to be touched

**Nadja, 2026-08-03.** No documented policy clause requires changing them, and editing them
alters a published live app.

Residual observation, recorded once and not re-argued: three of the eight public tools
(`create_priority`, `inspect_adapt`, `onboarding_calendar_setup`) contain
*"your default behavior is SUSPENDED"*, and `inspect_adapt` adds `FORBIDDEN:` and *"Override
analytical coaching impulses"*. The new deletion tool is clean of all five patterns —
verified programmatically. Whether that phrasing matters to a reviewer is a judgement call,
and the call has been made.

### 16.2 Remaining path to resubmission

1. Strike the 30-day verification log → unblocks Part D
2. Part D drafts the privacy-policy revisions
3. **Deploy backend + PG-Claude MCP only.** Hold PG-OpenAI until #10's mitigation ships —
   the two are separate Render services, and the `/delete-data` route is internal-secret
   gated, so a backend deploy alone does not expose the tool
4. Observe the confirmation dialog on Claude — the half of §12.6 only Nadja can do
5. Publish the policy revisions
6. Resubmit
