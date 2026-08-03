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

6. **Classify every category: delete / revoke-then-delete / retain.** Identifying which rows
   belong to PG is not sufficient. Each must carry a documented action, and the source of truth
   is **`Data_Retention_Strategy_Shared_Backend_Priority_Guardian_Suite_7.pdf` (project KB)**,
   not this briefing's assumptions.

   The retention strategy already specifies a deletion order — *"1. `sdk_app_name_*` tables,
   2. `core_consents` and `core_connections` (if revoked), 3. `core_users` last"* — and
   separately says consent records are *"retained to prove lawful processing"* with deletion
   triggered by **user revocation**. **Determine which applies when the user requests deletion
   rather than revocation, and report the conflict if the document does not resolve it.**

   Required classification table in your report:

   | Category | Action | Source |
   |---|---|---|
   | PG app tables (`pg_*`) | Delete | Retention strategy |
   | Google connection (`core_connections`) | Revoke at Google, then delete | Retention strategy |
   | `core_consents` (PG scopes) | **Determine** — delete vs retain-as-evidence | Retention strategy + report the ambiguity |
   | `oauth_access_tokens` (`pg.access`) | Revoke, then delete — **but note the strategy defines a 30-day "token audit log" on token metadata.** Establish whether that is a separate artefact or these rows. | Retention strategy |
   | `oauth_sessions` | **Retention strategy says these ARE deleted on account deletion.** This contradicts ADR_008 §1, which retains them. **Report the conflict; do not resolve it yourself.** | Retention strategy vs ADR_008 |
   | `core_tool_audit_log` | Retain — write, never delete | ADR_008 §3 |
   | `core_users` | Retain | ADR_008 §2 |

   **Two known conflicts to surface, not silently pick a side on:**
   - `oauth_sessions`: ADR_008 §1 retains them; the retention strategy deletes them on account
     deletion. Note this is *account* deletion, which may differ from *PG-scoped* deletion.
   - The retention strategy's verification-log entry says retain **30 days**;
     `core_tool_audit_log`'s own model comment and `cleanup_expired_audit_logs` say **90 days**.

   Getting this wrong in either direction is a compliance defect: deleting evidence the policy
   says is retained, or retaining user-linked data the deletion response claims is gone.

7. **Check non-SQL and deferred state.** Focused's implementation clears Redis cache keys.
   Determine whether PG writes any user-keyed state outside PostgreSQL, and report the key
   patterns or confirm there are none:
   - Redis cache keys containing `user_id` — the retention strategy specifies the purge pattern
     `redis.delete_pattern(f"{user_id}:*")`; verify it matches PG's actual key shapes
   - **Queued or retrying Celery jobs carrying a `user_id`** — a job that runs after deletion
     against a deleted user is a live failure mode
   - Cached or pre-rendered reports
   - Webhook subscriptions (`google_channel_id` / `google_resource_id` on `CoreConnection`)
8. **Deployed schema parity — report honestly, do not overclaim.** `alembic heads` shows the
   migration heads present in the *repository*. It does **not** establish which revision
   production is running, nor that the physical schema matches the ORM. Do:
   - `alembic heads` for repository state, and note any pending migration
   - `alembic current` against the **local test database** for local parity
   - **State explicitly that production schema parity is unverified**, because production
     database access is closed (empty IP allowlist, 2026-07-31) and §0.3 keeps you read-only.
     If parity matters before deploy, that is a human step for Nadja, not something you can
     assert.
9. **Backups — documentation, not deletion.** Deleting from active storage does not remove data
   from PostgreSQL backups. **The retention strategy already states the answer: encrypted
   backups retained 7 days, then automatically and permanently deleted.** Confirm that against
   Render's actual configuration and carry the figure into Parts D and F. **Not** into the
   deletion code.

**Output:** a table, the diff against ADR_008 §1, the shared-table filters, and an explicit
list of what you could not verify. **Then stop and wait for approval.** Do not begin Part B.

---

## 4. Part B — Backend deletion service and route

Only after Part A is approved and the inventory is agreed.

**Structure:** mirror Focused. A `delete_user_data()` function in PG's logic layer (Part A
establishes where that lives), called from a route on the existing offboarding router.

**Required sequence** — Focused's order, adapted:

1. Revoke the Google token **at Google** (external call, best-effort — see atomicity rules below).
2. Delete PG-owned tables per the verified inventory.
3. Delete PG-scoped rows from shared tables — **filtered by scope, never by `user_id` alone**.
4. Mark / delete the Google `CoreConnection` row per the inventory.
5. Write a `CoreToolAuditLog` entry: `app_name="priority_guardian"`, `action="delete_data"`,
   `result_status`, and a `details` dict with per-table row counts. **These four fields plus
   `user_id` and `created_at` are the complete model — verified 2026-08-01 in
   `backend/core/models.py`. Do not add fields to it.**
6. Return a structured result: success, tables affected, rows deleted per table, audit log id.

### ATOMICITY — mandatory, not a choice

An earlier draft of this briefing left the transaction boundary to your judgement. **It is now
specified.** A best-effort per-table sequence can leave priorities deleted, snapshots retained,
tokens half-removed, and return a failure after irreversible partial deletion. That is
unacceptable for an erasure operation the privacy policy will describe.

**Required architecture:**

- **All local PostgreSQL deletions plus the audit entry execute in ONE transaction.** Any local
  failure rolls back everything.
- **The Google revocation is an external call and sits outside that transaction.** Attempt it,
  record the outcome, and **do not block local deletion if Google is unreachable.** A user's
  erasure right must not depend on a third-party endpoint's availability.
- **The result must distinguish two things:** local PG data deleted (yes/no), and external
  Google revocation confirmed (yes / could not be confirmed). Never collapse them into one
  success flag.
- If Google revocation could not be confirmed, the connection row is still deleted locally and
  the audit entry records the unconfirmed revocation.

**The reverse case must also be handled: Google revoked, local transaction rolled back.**
Distributed atomicity is impossible here, so this outcome is acceptable — but it must not be
silent:

- Return an error that is **explicitly retryable**. Never report "nothing changed" — Calendar
  access is gone even though PG data remains.
- Emit an audit or error event recording the failed local attempt.
- **A retry must succeed even though Google is now disconnected.** The revocation step must
  tolerate an already-revoked or absent connection and proceed to local deletion. Test this
  path explicitly.

### The existing `/disconnect` cannot simply be called first

`backend/apps/priority_guardian/routers/offboarding_router.py::disconnect` **commits its own
transaction** (`await session.commit()`) and **returns early** when the user is already
disconnected. Calling it as step 1 would therefore break atomicity and skip the rest of the
flow on an already-disconnected user.

**Extract the revocation logic rather than calling the route.** Report how you did it — a
shared helper both paths call is the obvious answer, but do not restructure `/disconnect`'s
behaviour in the process (§2 puts it out of scope). If extraction would require changing
`/disconnect`, stop and report.

**Hard constraints:**

- **Never delete the `core_users` row.** State this in a comment at the deletion site, not only
  in the docstring.
- **Never delete `core_tool_audit_log` rows.**
- **Never delete `oauth_sessions`** — suite-level browser session, not PG state (ADR_008 §1).
- Idempotent: calling twice must succeed, with the second call reporting zero rows.
- Route requires `verify_internal_call` like every other PG route, and takes `X-User-ID`.

---

## 5. Part C — MCP tool, both PG servers

**Name:** something that says PG data, not "account". ADR_008 §4 — naming is load-bearing.

**Description must state:**
- what it deletes (priorities, goals, deliverables, snapshots, calendar connection, stored progress)
- that **other Priority Guard apps are unaffected**
- that it cannot be undone
- when to call and when not to

**Annotations — mandatory, not a decision:** `title` present, `readOnlyHint=False`,
`destructiveHint=True`, `openWorldHint=True`. **On BOTH platforms.** The tool permanently
deletes user data; Anthropic requires destructive tools to carry `destructiveHint: true`, and
both hosts use it to gate confirmation.

> **CORRECTED 2026-08-03.** This line previously mandated `openWorldHint=False`. That was
> wrong and it was mine. `openWorldHint` describes whether the tool interacts with an
> external, open system, and this one does — the backend revokes the user's token at Google.
> Every other PG tool that reaches Google through the backend sets it `True`
> (`get_priorities.py:332`, `get_priority_events`, `render_weekly_report`), so `False` would
> have contradicted the codebase's own convention and misdescribed the tool. Anthropic policy
> §2.B requires descriptions to precisely match actual functionality, and annotations are
> part of that.
>
> My reasoning when writing `False` was about gating the confirmation prompt — but
> `destructiveHint` does that alone; `openWorldHint` was never doing that work.
>
> Recorded rather than silently flipped. Claude Code implemented `False` as specified, then
> flagged the conflict instead of overriding it, which is what RULE 0a asks for.

**Do not use `_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES` for this tool.** That mechanism exists in
`mcp_server/priority_guardian_claude/tools_list_dupl.py` because `create_priority` is `False`
in the shared `ToolDefinition` — deliberately, to avoid ChatGPT's confirmation UI on a
creation tool — and needs raising to `True` on Claude. **A deletion tool wants that
confirmation on both platforms**, so set `destructive_hint=True` in the shared `ToolDefinition`
and add no override. Read that file to confirm the override dict is keyed by tool name and that
omitting an entry falls through to the shared value.

**Confirmation:** the user must confirm before deletion executes. **Use the platform's native
confirmation** — that is what `destructiveHint=True` triggers. Do not build a custom widget
confirmation unless you establish that the native behaviour is absent, and report the evidence
if you do. **Verify the confirmation actually appears on both platforms end to end** before
reporting this part complete; an annotation set correctly in code but not surfacing in the host
is the failure this check exists to catch.

**The user-facing result must describe categories, not schema.** Never surface table names,
audit-log IDs, or raw row counts to the user. Per-table counts belong in the audit entry and
the logs. Shape:

> **Deleted:** priorities, goals and deliverables; weekly progress snapshots; Priority Guardian
> configuration; the Google Calendar connection; Priority Guardian authorization data.
> **Retained:** a limited security audit record for up to 90 days; the shared suite identity
> other Priority Guard apps need.

The structured backend response may carry counts for testing and the widget; the text the user
reads may not.

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
- **Operation B** (suite-wide): **not implemented by this runbook, and not to be specified
  here.** An earlier draft gave a three-step sequence — PG deletion, MindSort deletion, then
  the `core_users` row. **That was under-verified and has been removed.** Suite-wide erasure
  needs its own verified inventory covering every published and deprecated app, shared consents,
  all OAuth grants and sessions, shared connections, audit retention, Redis, scheduled jobs and
  backups. Write instead:

  > Operation B is not yet implemented. Record the request and the 30-day clock. Do **not**
  > delete `core_users` until a verified suite-wide erasure procedure exists. Fulfil the
  > PG-scoped portion via Operation A and tell the requester what remains outstanding.
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
  timeout; PG tools use `TIMEOUT_S = 8.0` for backend calls. **Test at realistic maximum
  volume, not one row per table** — `pg_weekly_snapshots` accumulates weekly, so seed a user
  with the largest realistic set the retention model permits and measure. If it might exceed
  the timeout, report before implementing an async model rather than discovering it in
  production.
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
2. **Part A inventory**, the diff against ADR_008 §1, shared-table filters, **the per-category
   delete/revoke/retain classification (§3.6) with the two known conflicts surfaced**, and what
   you could not verify.
3. Per part: what changed, in which files, which requirement it satisfies.
4. Per test: what bug would still pass it. **Mutation results for the four §7 tests.**
5. **Atomicity evidence** (§4): how the single transaction is bounded, how Google revocation
   sits outside it, and how `/disconnect`'s own commit was handled without changing that route.
6. Confirmation verified end-to-end on **both** platforms (§5) — state how you verified it.
7. Timeout measurement at realistic maximum volume (§10).
8. Backup retention period, for Parts D and F (§3.8).
9. Anything you could not verify or had to assume — explicitly, not buried. **Production schema
   parity belongs here** (§3.7).
10. Adjacent issues noticed but not fixed — flagged only.
11. Deployment status and which services would redeploy on push.

**If any requirement is unclear, contradicts the codebase, or conflicts with a canonical
document: stop and report. Do not resolve the ambiguity by choosing.**
