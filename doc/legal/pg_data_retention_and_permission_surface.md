# Priority Guardian — Data Retention and Permission Surface

**Version:** 2.0 — merged and updated
**Status:** Verified against codebase 2026-08-04
**Parent document:** Shared Backend Data Retention Strategy v1.0 — **PDF only, not in this
repository.** The markdown transcription was removed 2026-08-04; this document is the
in-repo record for Priority Guardian.
**Related:** `doc/ADR/ADR_006_token_revocation_semantics.md`, `doc/ADR/ADR_007_user_identity_and_lifecycle.md`, `doc/ADR/ADR_008_data_ownership_and_deletion_model.md`

> **Supersedes two documents**, merged 2026-08-04 because they duplicated the shared-tables
> inventory, the Google field-filtering section and the Implementation Gaps section verbatim,
> and both were stamped *"verified 2026-03-03"*:
>
> - *Priority Guardian Suite — Data Retention: Priority Data* (v1.4)
> - *What PG Actually Accesses/Stores — The Full Permission Surface* (v1.3)
>
> **Changelog v1.3/1.4 → 2.0:** Claude added as a distribution platform. Anthropic added as an
> independent controller. `delete_my_priority_guardian_data` and `core_tool_audit_log` writes
> implemented — the sole Implementation Gap is closed. Deletion split into Operation A /
> Operation B. `oauth_authorization_codes` added to the deletion inventory. Redis and
> `login_hint` claims corrected. Residual access window documented. Two conflicts flagged in
> §10.

---

## Governing principles (inherited)

- **Purpose limitation** (Art. 5(1)(b)) — priority tracking, weekly progress reporting only
- **Storage limitation** (Art. 5(1)(e))
- **Data minimisation** (Art. 5(1)(c)) — enforced at the Google API request level, §2
- **Cross-app scope** — `core_users` and `core_consents` are shared only for lawful
  interoperability across the suite, never combined for analytics or profiling. `pg_*` tables
  are strictly PG-scoped.

---

## 1. Platforms

PG runs on **two** platforms through separate MCP servers sharing one backend and one
authorization server.

| | ChatGPT | Claude |
|---|---|---|
| MCP server | `priorities-guard-pg-mcp` | `priority-guardian-claude-mcp` |
| Resource URL | `https://pg.priority-guard.com/mcp` | `https://mcp.priority-guard.com/mcp` |
| Runtime processor | OpenAI (data processor, signed DPA) | Anthropic (**independent controller** — §6) |
| Cross-device identity | `openai_subject` reconciliation | Claude account holds the OAuth grant |
| Status | Published, live | Awaiting directory resubmission |

---

## 2. Google Calendar — external access

### Scopes

| Scope | Reads | Does not |
|---|---|---|
| `calendar.events.readonly` | summary, description, start/end, status, event ID, attendee `self` + `responseStatus` | No write, modify or delete. No attendee identities, locations, or recurrence rules. |
| `calendar.settings.readonly` | timezone only | No modification; no other settings |

### Field filtering — implemented

`fetch_events()` and `list_events()` in `google_calendar.py` pass an explicit `fields`
parameter:

- `fields=items(id,summary,description,start,end,status,attendees(self,responseStatus))`
- list variant adds `,nextPageToken`

Google never sends `location`, `creator`, `organizer`, `attachments`, `conferenceData`,
`reminders`, `htmlLink` or `hangoutLink`. Art. 5(1)(c) satisfied at the request level, not by
discarding after receipt.

### Two read paths

**Path 1 — keyword matching and hour computation** (`calendar_service.compute_allocation_from_events`).
Runs for all weeks. Nothing persisted except computed hours.

| Field | Purpose |
|---|---|
| `summary` | `\bP[123]\b` word-boundary keyword match |
| `start`/`end` `dateTime` | duration, 2dp |
| `start.date` | detect all-day events (excluded) |
| `attendees[].self` + `responseStatus` | exclude events the user declined |
| `status` | exclude cancelled |
| `id` | in-memory dedup within a week |

**Path 2 — semantic grouping** (`weekly_report_service.process_events_for_report`).
**Current week only**; past weeks return `allEvents: []`.

Titles, descriptions, start/end times and matched keywords are included in `allEvents` and
therefore **leave the EU** to reach the ChatGPT or Claude runtime. Never written to any PG
table.

### Limited-use compliance

Calendar data is used solely for per-priority time allocation and conversational semantic
grouping. Not used for advertising, analytics, profiling or model training. Not sold or
transferred to data brokers.

---

## 3. Storage inventory

### PG-owned tables

| Table | Contents | Constraints |
|---|---|---|
| `pg_priorities` | name (100), type, `calendar_keyword` (P1/P2/P3), deadline, `weekly_hour_target`, `checkpoint_date`, status, plus running aggregates `streak_count`, `total_hours_invested`, `avg_target_achievement`, `retired_at` | Partial unique index: one active keyword per user. Check constraints enforce type↔field consistency. |
| `pg_goals` | `text` (200), `achieved` | FK → `pg_priorities`, CASCADE. Max 3 per priority, API-enforced. |
| `pg_deliverables` | name (200), `done` | FK → `pg_priorities`, CASCADE. |
| `pg_weekly_snapshots` | `actual_hours`, `target_hours`, `streak_at_snapshot`, `calendar_keyword_at_snapshot`, `other_hours`, `total_tracked_hours`, `week_start`, `week_end` | Unique on (`priority_id`, `week_start`). Immutable. **Dual FK** — CASCADEs from *either* `pg_priorities` or `core_users`. |

### Shared tables PG uses

| Table | PG's use | Retention | On PG deletion (Operation A) |
|---|---|---|---|
| `core_users` | identity (UUID ↔ platform pseudonymous ID) | until full account deletion | **Retained** — shared infrastructure (§5) |
| `core_connections` (`provider=google`) | Google OAuth tokens, AES-256, revocation state | until revoked or 6-month inactivity | Revoked at Google, then deleted |
| `core_consents` (`app_name=priority_guardian`) | per-scope consent records | persistent until revoked | Deleted, PG-scoped rows only |
| `core_tool_audit_log` | audit trail: disconnect, deletion | 90 days rolling | **Retained** — written, never deleted (§5) |
| `oauth_access_tokens` (`pg.access`) | platform ↔ PG auth | 1h access / 30d refresh | Revoked, then deleted |
| `oauth_authorization_codes` (`pg.access`) | authorization flow, PKCE | 10 min TTL | Deleted |
| `oauth_sessions` | cross-app browser session | **30 days sliding** (`SESSION_LIFETIME_DAYS`), extended on each successful lookup | **Retained** — suite-level, not PG state |
| Redis | ephemeral | TTL | Not purged — **see §4** |

### Computed, never stored

Time allocation beyond the persisted hours; semantic groupings (LLM-produced, non-deterministic,
recomputed each report, current week only); pattern analysis (`pattern_service.py`, read-only
queries over existing snapshots).

### Columns removed (data minimisation, 2026-03-03)

`oauth_access_tokens.last_used_at`; `oauth_sessions.session_token` (plaintext → hash + Fernet);
`oauth_authorization_codes.nonce` (OIDC, unused); `clarity_clusters.thoughts_exhausted` and
`.correctly_clustered`.

---

## 4. Non-SQL state — verified 2026-08-04

| | Finding |
|---|---|
| **Redis** | PG writes **no** keys in a `{user_id}:*` namespace. The shared backend strategy's `redis.delete_pattern(f"{user_id}:*")` step is a no-op for PG. The only user-keyed Redis state is `oauth:auth:<id>` written by the shared OAuth layer (10-minute TTL). **Allowed to expire; not purged on deletion** — adding a Redis dependency to a transaction that has none is the worse trade. |
| **Celery** | No task carries a PG `user_id`. `renew_google_token` and `renew_webhook` are unimplemented stubs — no decorator, not in `beat_schedule`. All eight scheduled tasks are sweeps. |
| **Webhooks** | PG registers none. Only Focused (deprecated) used `google_channel_id` / `google_resource_id`. |
| **Cached reports** | None outside `pg_weekly_snapshots`. |

*Correction: an earlier analysis reported "Redis: none" by searching `backend/apps/priority_guardian/` only. The state lives in the shared OAuth layer. The app-directory boundary is not the data boundary.*

---

## 5. Deletion

### Two operations (ADR_008 §4)

| | **A — Delete my Priority Guardian data** | **B — Delete all suite data** |
|---|---|---|
| Trigger | `delete_my_priority_guardian_data` MCP tool | support email, manual runbook |
| Scope | PG-owned + PG-scoped shared rows | every app + `core_users` |
| Status | **Implemented 2026-08-04** | **Not implemented** |
| `core_users` | retained | deleted |

**Naming is load-bearing.** The tool deletes *Priority Guardian data*, not the account. A
MindSort AI board is untouched.

### Operation A sequence

1. Revoke the Google token at Google — **outside** the DB transaction, bounded at 3s,
   best-effort. Failure is recorded, never blocks local deletion.
2. Delete `pg_priorities` children first (`pg_weekly_snapshots`, `pg_deliverables`, `pg_goals`),
   then `pg_priorities` — child-first so per-table counts are real rather than zeroed by cascade.
3. Delete PG-scoped rows from shared tables, **filtered by app name or scope, never by
   `user_id` alone**.
4. Write a `CoreToolAuditLog` entry: `app_name`, `action="delete_data"`, `result_status`,
   per-table counts.
5. Steps 2–4 execute in **one transaction**. Any local failure rolls back everything and
   returns an explicitly retryable error.

### Why `core_users` is retained

Architectural, not legal: it is the shared anchor for every app in the suite and everything
cascades from it. Deleting it during an app-scoped request would destroy data the user did not
ask to delete. `backend/apps/focused/logic/offboarding.py` encodes the same rule.

A PG-only user's row survives as an empty shell until the six-month inactivity cleanup.

### Why `core_tool_audit_log` is retained

Deliberately not a foreign key — *"audit logs must persist after user deletion for GDPR
compliance."* Expires independently at 90 days via `cleanup_expired_audit_logs`. Deletion
**writes** here; it never deletes from here.

### Other deletion paths

**Delete a priority** — cascades to goals, deliverables, snapshots.
**Retire a priority** — `status=retired`, aggregates frozen, children retained read-only.
**Disconnect** (`POST /pg/disconnect`) — revokes Google, marks the connection revoked, marks
`pg.access` tokens revoked. **Priority data is not deleted.** See §7.
**Inactivity cleanup** — 6 months with no active connection or consent. A retention control,
**not** a request-fulfilment mechanism.

---

## 6. Processors and controllers

| Party | Role | Basis | Location |
|---|---|---|---|
| **OpenAI** | ChatGPT runtime | **Processor** under signed DPA; SCCs; EU/EEA processing by OpenAI Ireland Ltd. | US |
| **Anthropic PBC** | Claude runtime | **Independent controller.** Processes under its own agreement with the user, *not* a DPA with us — its published DPA covers API/Commercial customers submitting data through its Services, which is not this architecture. | US |
| **Render** | hosting, PostgreSQL, Redis | Processor; DPA; EU-US DPF | Frankfurt (EU) |
| **IONOS** | support email forwarding | Processor | Germany (EU) |
| **Google** | Calendar API | Independent controller | US, EU-US DPF |

---

## 7. Access after deletion or disconnect (ADR_006)

**Resource servers validate tokens statelessly via JWKS.** No revocation lookup, no database
access, no user-existence check.

Consequences to state accurately anywhere this is described:

- A token issued before deletion remains **technically valid** for up to
  `OAUTH_TOKEN_EXPIRY_SECONDS + TOKEN_EXPIRY_GRACE_SECONDS` (60m30s at code defaults, both
  env-derived). The data is already gone, so nothing can be read.
- **Disconnect revokes Google Calendar only.** Nothing is revoked at the authorization server.
  The `/oauth/*/revoke` endpoint is mounted and functional but has never been called by either
  platform in 30 days of logs.
- **"Access was immediately terminated" is not a true sentence.** Neither is "your data is
  deleted everywhere, now" — backups expire on their own 7-day schedule.

---

## 8. Identity (ADR_007)

`CoreUser.id` is the **canonical application identity**. Platform identifiers are opportunistic
mappings, not the identity.

| | ChatGPT | Claude |
|---|---|---|
| `login_hint` | **Dead** — never sent in production | n/a |
| Session cookie | fallback at authorize time | fallback at authorize time |
| Tool-call reconciliation | **`openai_subject`**, Increment 78 — partial unique index, A/B/C1/C2/X contract | **none** — Anthropic exposes no per-user identifier |
| Net | stable across browsers and devices | stable while the grant lives |

**Consequence for support:** `CoreUser` stores only `id`, `chatgpt_user_id`, `openai_subject`,
`created_at` — no email, no name. An emailed request carries no field that maps to a row.
**Authenticated operations resolve identity correctly; unauthenticated ones cannot be reliably
matched.** In-app deletion is therefore the primary route and email the exceptional one.

`openai_subject` is written to logs as a truncated SHA-256 fingerprint, never raw
(2026-08-04).

---

## 9. Data subject rights

| Right | Art. | Route |
|---|---|---|
| Access | 15 | `get_priorities`, `render_weekly_report` in-app; email for full export |
| Rectification | 16 | widget tools — self-service |
| **Erasure** | **17** | **`delete_my_priority_guardian_data` in-app (primary).** Per-priority deletion also available. Suite-wide: email, manual. |
| Restriction | 18 | retirement — retained but frozen |
| Portability | 20 | email; **subject to the §8 identification limit** |
| Objection | 21 | retire or delete at any time; no automated profiling |

30-day response per Art. 12(3) — a commitment stricter than the statutory month.

---

## 10. Conflicts — both resolved 2026-08-04

### 10.1 `oauth_sessions` retention — RESOLVED 2026-08-04

| Source | Value | Verdict |
|---|---|---|
| Published privacy policy §8 and §11 | 30 days sliding | **Correct** |
| Predecessor documents v1.3 / v1.4 | 2 years sliding | **Stale** |

`backend/core/oauth_provider/services/session_service.py` sets
`SESSION_LIFETIME_DAYS = 30`, with the comment *"reduced from 2 years to limit shared-device
leakage window."* Applied at both creation and sliding-window extension in `get_session_user`.

The predecessor documents inherited "2 years" from Increment 19 and were never updated when the
value changed. **The published privacy policy requires no change on this point.**

*One stale artefact remains:* one docstring in `create_session` still reads *"Calculate
expiration (730 days from now)"* immediately above a line that uses the 30-day constant. The
code is correct; the comment is not. Cosmetic — file as cleanup.

> **Retention on deletion is unchanged by this.** `oauth_sessions` is still **retained** on
> Operation A (suite-level browser session, not PG state — §3) and deleted on Operation B via
> `delete_user_sessions()`.

### 10.2 30-day verification log — struck

The shared backend strategy specifies a post-deletion verification record retained 30 days.
**No writer exists anywhere in the codebase** (verified 2026-08-04). Struck; superseded by
`core_tool_audit_log` at 90 days, which is implemented and swept.

---

## 11. Status against the shared backend strategy

| Requirement | Status |
|---|---|
| FK CASCADE on all app tables | ✅ |
| Purpose-scoped `pg_*` tables | ✅ |
| 90-day audit log retention | ✅ **PG now writes to it** (2026-08-04) |
| Verification log after deletion | ✅ via `core_tool_audit_log` (§10.2) |
| 6-month inactivity cleanup | ✅ inherited |
| AES-256 at rest / TLS 1.3 in transit | ✅ |
| EU-only hosting | ✅ Render Frankfurt |
| Pseudonymous IDs only | ✅ |
| Rights via support email | ✅ Tier 1 |
| `delete_my_data` MCP tool | ✅ **Implemented** as `delete_my_priority_guardian_data` |
| `delete_user_data(user_id)` Celery job | **Superseded** — synchronous, one transaction, ~30ms for 621 rows. A Celery job would add failure modes for no benefit. |
| Redis purge in deletion workflow | **N/A** — §4 |
| Data export endpoint | Tier 2, not implemented |
| Post-retirement snapshot cleanup | Tier 2, not implemented |
| `sdk_app_name_onboarding_state` | N/A — PG onboarding is conversational |
| `sdk_app_name_scheduled_jobs` | N/A — no PG-specific scheduled jobs |

**Implementation Gaps: none open.** The single gap in v1.3/v1.4 — *"PG does not write to
`core_tool_audit_log`"* — closed 2026-08-04.

---

## 12. ROPA extension

| Field | Value |
|---|---|
| Processing activity | Priority Guardian — priority tracking, time allocation, progress reporting |
| Controller | Nadja Carabulea |
| Processors | OpenAI (ChatGPT runtime), Render (hosting, DB, Redis), IONOS (email) |
| Independent controllers | Anthropic PBC (Claude runtime), Google LLC (Calendar API) |
| Data subjects | ChatGPT and Claude users who connect Priority Guardian |
| Data categories | Priority configuration, goals, deliverable status, weekly time aggregates, pseudonymous platform user ID. Current-week event titles and descriptions transferred to the platform runtime for semantic grouping; not stored. |
| Lawful basis | Consent, Art. 6(1)(a) |
| Special categories | None requested or required. Free-text fields cannot enforce this — users are asked not to enter Art. 9 data (§13). |
| International transfers | EU → US for OpenAI (SCCs) and Anthropic (own mechanisms). All storage in EU, Render Frankfurt. |
| Security | AES-256 at rest, TLS 1.3 in transit, pseudonymisation, sole-developer MFA access, automated retention deletion |

---

## 13. Free-text fields

PG collects user-authored free text in `pg_priorities.name` (100) and `pg_goals.text` (200).
Users are asked not to enter personal or sensitive data. This is **UX-level guidance, not
backend validation** — free-text fields cannot enforce it. Art. 9 data is not requested or
required, but its absence cannot be guaranteed. Relevant wherever proportionality is used to
justify an accepted risk.

---

## What Claude Code must know

1. **Never delete `core_users` in an app-scoped deletion.** Shared; cascading it destroys other
   apps' data.
2. **Never delete `core_tool_audit_log` rows.**
3. **Filter shared tables by app name or scope, never by `user_id` alone.**
4. **`pg_weekly_snapshots` has a dual FK** — it cascades from `core_users` as well as
   `pg_priorities`. It disappears even when not named.
5. **Adding a PG-owned state table requires extending the fresh-shell check** in
   `reconcile_router.py` — see the warning at the top of `doc/OPERATIONS_MIGRATIONS.md`.
6. **The app-directory boundary is not the data boundary.** Searching
   `backend/apps/priority_guardian/` alone has twice missed shared-layer state.
