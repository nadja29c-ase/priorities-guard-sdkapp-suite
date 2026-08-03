# Increment: Priority Guardian — Authenticated Data Deletion

**Version:** 1
**Platform:** Both — shared backend, PG-OpenAI MCP, PG-Claude MCP
**Type:** Compliance + product completion
**Trigger:** PG has no user-initiated deletion path on either platform. `offboarding_router.py`
exposes `/disconnect` only; its docstring records *"No DELETE /delete-data yet (later
increment)."* This is that increment.

---

## 0. Read first

### 0.1 The decisions are already made — do not re-open them

`doc/ADR_008_data_ownership_and_deletion_model.md` records the deletion model, the data
ownership table, the identification model, and five rejected alternatives. It was written after
working through those alternatives; re-proposing any of them wastes the round.

**Read ADR_008 in full before anything else.** The five rules in its "What Claude Code Must
Know" section are binding.

`doc/ADR_007_user_identity_and_lifecycle.md` explains why identification is a non-problem on
this path: the JWT carries `sub`, which resolves to `CoreUser.id`. **There is no identification
step in this increment.**

### 0.2 The three ways this increment can cause irreversible harm

Deletion code is the highest-consequence code in the suite. Three specific failure modes:

| # | Mistake | Consequence |
|---|---|---|
| 1 | Deleting the `core_users` row | Cascades to **every** app. A MindSort user loses their board. Irreversible. |
| 2 | Filtering shared tables by `user_id` alone | Deletes MindSort's consents and tokens along with PG's. Silently breaks their connector. |
| 3 | Missing a PG table in the inventory | Data the user asked to delete survives. A false compliance claim in a published policy. |

Mistakes 1 and 2 are worse than not shipping. **When uncertain, stop and report rather than
choosing.**

### 0.3 Deployment posture

- Backend `autoDeploy: no` — commits do not ship.
- PG-Claude (`priority-guardian-claude-mcp`) `autoDeploy: no`.
- PG-OpenAI (`priorities-guard-pg-mcp`) — **check before committing.** If it auto-deploys from
  `main`, this work goes on a branch.
- PG-OpenAI is a **published live app with ~94 live grants**. PG-Claude is awaiting
  resubmission. Both are real users.

Render access is **read-only** for you: no env writes, no manual deploy triggers.

---

## 1. Canonical guidance — read before writing anything

- `doc/ADR_008_data_ownership_and_deletion_model.md` — **the decisions**
- `doc/ADR_007_user_identity_and_lifecycle.md` — why identification is already solved
- `doc/ADR_006_token_revocation_semantics.md` — disconnect vs deletion; the four-trigger table
- `doc/OPERATIONS_PREDEPLOY.md`, `doc/OPERATIONS_MIGRATIONS.md`, `doc/OPERATIONS_PRESUBMISSION.md`
- `doc/Claude_Compliance/claude_connectors_compliance_master.md` — tool annotations
- `doc/compliance_master_1.3.26.md` + `doc/openai_uiux_1.3.26.md` — ChatGPT-side tool rules
- **Live** privacy policy at `https://www.fulfilling-productivity.com/pg-privacy-policy` —
  **fetch it.** The repo copy `doc/legal/pg_privacy_policy_v3.1.md` is two versions stale and
  produced a false finding in a previous increment.

**Reference implementation:** `backend/apps/focused/logic/offboarding.py::delete_user_data`.
Copy the pattern. Do not redesign it. It already encodes the `core_users` rule.

---

## 2. Scope

| Part | Deliverable | Gate |
|---|---|---|
| **A** | **Inventory verification — no code** | Gates everything |
| B | Backend deletion service + route | After A is approved |
| C | MCP tool on both PG servers | After B |
| D | Privacy policy update — draft only | After A |
| E | Tests | Alongside B/C |
| F | `OPERATIONS_ERASURE.md` runbook | After B |

**OUT OF SCOPE — flag, do not fix:**
- MindSort's `delete_my_data` scope inconsistency (ADR_008 §7.2)
- An authenticated **export** tool (ADR_008 §7.3) — same identification story, separate work
- Suite-wide deletion (Operation B) — runbook only, no code
- Any change to `/disconnect`
- Any OAuth, audience, or identity code
- Publishing the privacy policy — you draft, Nadja publishes

---

## 3. Part A — Inventory verification (do this first, no code)

**The inventory in ADR_008 §1 is a reconstruction from reading models. It has not been verified
against the live schema. Verify it. Report. Stop.**

1. **Enumerate every table that stores PG user data.** Read
   `backend/apps/priority_guardian/db_models.py` in full. Then search the whole backend for
   models with a `user_id` column or a FK chain reaching `core_users.id`. Do not rely on the
   ADR's list — build yours independently and then diff against it.
2. For each table found, record: name, how it links to the user (direct `user_id` or transitive
   via which FK), `ondelete` behaviour, and whether ADR_008 §1 lists it.
3. **Report any table the ADR missed, and any table the ADR lists that does not exist.**
4. **Trace the cascade paths.** If `pg_goals` cascades from `pg_priorities`, deleting priorities
   removes goals automatically — deleting both explicitly is harmless but the report must state
   which deletions are explicit and which are cascade effects, because the test assertions
   differ.
5. **Identify every shared table PG writes to** (`core_connections`, `core_consents`,
   `oauth_access_tokens`, `oauth_sessions`, `core_tool_audit_log`) and state **exactly what
   filter** isolates PG's rows from MindSort's. For `core_consents` and `oauth_access_tokens`
   this is a scope filter — name the literal scope value. **If any shared table has no reliable
   PG-only filter, stop and report: that is a blocker, not a detail.**
6. **Check Redis.** Focused's implementation clears Redis cache keys. Determine whether PG
   writes any user-keyed Redis state and, if so, the key patterns.
7. **Confirm the deployed schema matches the models.** Run `alembic heads` and check for
   pending migrations. A model-schema mismatch means the inventory is wrong in a way reading
   cannot detect.

**Output:** a table, the diff against ADR_008 §1, the shared-table filters, and an explicit
list of what you could not verify. **Then stop and wait for approval.** Do not begin Part B.

---

## 4. Part B — Backend deletion service and route

Only after Part A is approved and the inventory is agreed.

**Structure:** mirror Focused. A `delete_user_data()` function in PG's logic layer (Part A
establishes where that lives), called from a route on the existing offboarding router.

**Required sequence** — Focused's order, adapted:

1. Call the existing disconnect logic first (revoke Google, mark connection revoked). If already
   disconnected, continue.
2. Delete PG-owned tables per the verified inventory.
3. Delete PG-scoped rows from shared tables — **filtered by scope, never by `user_id` alone**.
4. Write a `CoreToolAuditLog` entry: `app_name="priority_guardian"`, `action="delete_data"`,
   `result_status`, and a `details` dict with per-table row counts.
5. Return a structured result: success, tables affected, rows deleted per table, audit log id.

**Hard constraints:**

- **Never delete the `core_users` row.** State this in a comment at the deletion site, not only
  in the docstring.
- **Never delete `core_tool_audit_log` rows.**
- **Never delete `oauth_sessions`** — suite-level browser session, not PG state (ADR_008 §1).
- Idempotent: calling twice must succeed, with the second call reporting zero rows.
- Partial failure must not leave a half-deleted state silently. Decide transaction boundaries
  deliberately and **state the choice and its rationale in the report** — Focused's best-effort
  per-table approach is one valid answer, a single transaction is another. Do not copy without
  deciding.
- Route requires `verify_internal_call` like every other PG route, and takes `X-User-ID`.

---

## 5. Part C — MCP tool, both PG servers

**Name:** something that says PG data, not "account". ADR_008 §4 — naming is load-bearing.

**Description must state:**
- what it deletes (priorities, goals, deliverables, snapshots, calendar connection, stored progress)
- that **other Priority Guard apps are unaffected**
- that it cannot be undone
- when to call and when not to

**Annotations:** `title`, `readOnlyHint=False`, `destructiveHint=True`, `openWorldHint=False`.

**Note the existing pattern:** `mcp_server/priority_guardian_claude/tools_list_dupl.py` carries
`_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES` because ChatGPT shows confirmation UI on
`destructiveHint=True` for public tools. Read that file and decide whether this tool needs the
same treatment, or whether `True` on both platforms is correct here. **State the decision and
why.**

**Confirmation:** the user must confirm before deletion executes. Determine from the existing
tool patterns whether this is a two-call flow, a widget confirmation, or model-driven — do not
invent a new mechanism.

**Both servers.** The tool registry is shared (`mcp_server/priority_guardian/tools/`), so one
definition serves both. Verify that assumption against `tools_list_dupl.py` rather than assuming
it.

---

## 6. Part D — Privacy policy update (draft only)

**Fetch the live policy first.** Draft revisions to the sections describing deletion and
retention. Do not publish.

Must accurately describe:
- in-app deletion as the primary route, and what it removes
- that other Priority Guard apps are unaffected
- disconnect vs deletion — different operations (ADR_006)
- what is retained and why: audit log (90 days, disclosed), pseudonymous internal identifier
- six-month inactivity cleanup as a backstop, **not** as the request-fulfilment mechanism
- the support route, in the shape agreed in ADR_008 §5 — no promise that email always works

**Do not** re-introduce a promise the implementation cannot keep. That mismatch is what this
increment exists to remove.

---

## 7. Part E — Tests

**Unit:** deletion logic with mocked session — correct tables targeted, correct filters,
audit log written, idempotency.

**Integration** — isolated test DB, verify `DATABASE_URL` resolves to it and print the host
before running.

The four that matter most:

1. **`core_users` survives.** Create a user with PG data, delete, assert the row still exists.
2. **Cross-app isolation.** Create a user with **both** PG data and MindSort data. Delete PG
   data. Assert **every** MindSort row is untouched. This is the test that catches failure
   modes 1 and 2 from §0.2.
3. **Complete deletion.** Assert zero rows remain in every table from the verified inventory.
   Derive the assertion from the inventory list, not from a hand-copied list — a hardcoded list
   silently stops covering a table added later.
4. **Audit log written and retained**, with correct app name and row counts.

Plus: idempotency, deletion of a user with no data, and shared-table scope filtering asserted
per table.

**Mandatory discipline:** for every test, state what bug would still pass it. **And
mutation-verify the four above** — break the behaviour in source, confirm the test fails,
restore byte-identically. A previous increment shipped three assertions that could not fail;
each was the load-bearing test of its file. Do this before reporting green, not after being
asked.

---

## 8. Part F — `doc/OPERATIONS_ERASURE.md`

The manual runbook for the exceptional support path.

- **Operation A** (PG data, connected user): direct them to the in-app tool. That is the answer.
- **Operation B** (suite-wide): the manual sequence — PG deletion, MindSort deletion, then the
  `core_users` row. Include the actual steps.
- **Identification:** per ADR_008 §5. Case-by-case investigation for the disconnected user.
  **Do not write a deterministic procedure based on priority names or keywords** — that was
  explicitly rejected.
- The 30-day response clock the published policy commits to.
- What is retained and why.

---

## 9. Implementation approach — Copy and Adjust, Never Rewrite

1. Read each file in full first.
2. Make only the changes listed here.
3. Do not restructure, rename, reformat, or improve anything not listed — including comments,
   docstrings, imports, type hints.
4. Preserve existing comments; several encode incident history.
5. If a change appears to require restructuring, stop and report.
6. `git checkout`/`restore` of a tracked file requires `git stash push` first.
7. Verify your own work against `git show <sha>:<path>`, not the working tree.

---

## 10. Production readiness

- **Scalability:** deletion is rare and user-initiated. No hot-path impact. Bound the work if
  any table could hold many rows per user (`pg_weekly_snapshots` accumulates weekly).
- **GDPR:** this increment exists to make the erasure right executable. It adds no new personal
  data. Never log deleted content — row counts only, never priority names or board text.
- **Latency:** deletion touches several tables. Confirm it completes inside the MCP tool
  timeout; PG tools use `TIMEOUT_S = 8.0` for backend calls. **If it might exceed that, report
  rather than silently accepting a timeout risk.**
- **Cross-platform:** the tool ships to a live published ChatGPT app and a Claude connector
  awaiting resubmission. Both must work.

---

## 11. Pre-deploy gate

- Read `doc/OPERATIONS_PREDEPLOY.md` in full and execute every applicable item.
- Read `doc/OPERATIONS_MIGRATIONS.md` — **including the fresh-shell warning at the top.** If this
  increment adds no table, that warning does not fire; **state that explicitly.**
- Run the full suite. Report the delta against `doc/testing_baseline_2026-07-04.md`, and note
  that the baseline is known stale (5 documented vs 34 actual).
- Confirm whether a `WIDGET_VERSION` bump is required.

---

## 12. Definition of done — report requirements

1. **Commit SHA.** No SHA, no review.
2. **Part A inventory**, the diff against ADR_008 §1, shared-table filters, and what you could
   not verify.
3. Per part: what changed, in which files, which requirement it satisfies.
4. Per test: what bug would still pass it. **Mutation results for the four §7 tests.**
5. The transaction-boundary decision and its rationale (§4).
6. The `destructiveHint` decision for both platforms (§5).
7. Timeout assessment (§10).
8. Anything you could not verify or had to assume — explicitly, not buried.
9. Adjacent issues noticed but not fixed — flagged only.
10. Deployment status and which services would redeploy on push.

**If any requirement is unclear, contradicts the codebase, or conflicts with a canonical
document: stop and report. Do not resolve the ambiguity by choosing.**
