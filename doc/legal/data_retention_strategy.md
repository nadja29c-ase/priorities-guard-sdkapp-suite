# Data Retention Strategy — Shared Backend, Priority Guard Suite

**Status:** Transcription of `Data_Retention_Strategy_Shared_Backend_Priority_Guardian_Suite_7.pdf`
**Transcribed:** 2026-08-01
**Purpose:** make the retention model readable from the repository. The PDF lives outside the
tree and was unreachable to tooling, which blocked §3.6 of the PG deletion increment.

> **This document is a transcription, not a rewrite.** Where the source is ambiguous or
> conflicts with code, the conflict is recorded in §7 rather than resolved in place. Two such
> conflicts exist and both have recorded decisions. **The PDF remains the signed artefact**;
> if the two ever diverge, reconcile deliberately rather than assuming this file is current.

---

## 1. Controller and infrastructure

| | |
|---|---|
| Controller | Nadja Carabulea (developer / publisher) |
| Hosting | Render, Frankfurt (EU). PostgreSQL and Redis both in EU data centres. |
| Lawful basis | User consent, Art. 6(1)(a) |
| Data protection contact | `support@priority-guard.com` |

**Processors:** OpenAI (ChatGPT runtime), Render Services Inc. (hosting, PostgreSQL, Redis),
IONOS SE (support email forwarding). **Google LLC is a service provider, not a processor** —
Calendar access is by user OAuth consent and Google acts as an independent controller.

**Transfers:** EU → US occurs during normal operation when MCP tool responses reach the
ChatGPT runtime. Pseudonymous app data only — priority names, goal text, deliverable names,
aggregated hours, pattern descriptions. No direct identifiers. Governed by OpenAI's SCCs.

> **Note (2026-08-01):** the source predates Claude distribution. Anthropic is not listed. The
> published privacy policy v3.2 does list Anthropic; see ADR_007 and the policy for the current
> position. **This transcription does not add it** — that is a change to the source document,
> not a transcription decision.

---

## 2. Retention table

| Data | Table / storage | Retention | Deletion trigger |
|---|---|---|---|
| User identity | `core_users` | Until full account deletion | User requests full deletion |
| ChatGPT user ID (pseudonymous) | `core_users.chatgpt_user_id` | While any linked data exists | After all linked app data and consents are deleted, anonymize or delete |
| Anonymized ChatGPT subject | `core_users.openai_subject` | Tied to `CoreUser` lifecycle | Full deletion, or 6-month inactivity cleanup |
| Consent records | `core_consents` | **Persistent until user revokes** | User revocation |
| OAuth tokens (Google, outbound) | `core_connections` | Until revoked or 6 months inactivity | Revocation or 6 months idle |
| ChatGPT OAuth access tokens | `oauth_access_tokens` | 1 hour | Expiry |
| ChatGPT refresh tokens | `oauth_access_tokens` | 30 days | Expiry |
| OAuth authorization codes | `oauth_authorization_codes` | 10 minutes | Expiry / single use |
| Token audit log | `oauth_access_tokens` metadata | 30 days | Traceability and security auditing |
| Audit logs (tool executions) | `core_tool_audit_log` | 90 days | Rolling delete beyond 90 days |
| Browser session cookie | `pg_session` → `oauth_sessions` | 30 days sliding | Expiry (Celery cleanup), **or immediately when the user deletes their account** |
| Onboarding progress | `*_onboarding_state` | Delete once complete | `onboarding_complete = true` |
| Scheduled jobs | `*_scheduled_jobs` | Until execution + 7 days | Auto-purge completed > 7 days |
| Redis cache | in-memory | TTL 1h – 30d | Auto-expire |
| PostgreSQL backups | Render managed | **7 days, encrypted** | Automatic permanent deletion after 7 days |

**Cross-app scope:** data in `core_users` and `core_consents` is shared only for lawful
interoperability across the suite. Never combined for analytics, profiling or marketing.

**Inactivity cleanup:** accounts with no active OAuth connections or consents for ≥ 6 months are
automatically anonymized or deleted.

---

## 3. Deletion mechanism — as specified in the source

Cascading delete via an event-driven Celery job. `delete_user_data(user_id)` deletes
sequentially from:

1. `sdk_app_name_*` tables
2. `core_consents` and `core_connections` (**if revoked**)
3. `core_users` **last**

Plus: Redis purge in the same workflow (`redis.delete_pattern(f"{user_id}:*")`), FK CASCADE at
the database level, and a verification log line written to `core_tool_audit_log`
(`user_id`, `timestamp`, `tables_affected_count`) **retained 30 days** to prove deletion.

> **This describes a suite-wide operation** (`core_users` last). ADR_008 §4 splits deletion into
> Operation A (app-scoped) and Operation B (suite-wide). The sequence above corresponds to
> **Operation B**, which is not implemented. See §7.1.

---

## 4. Tier model

| Tier | Mechanism | Status |
|---|---|---|
| **Tier 1 — MVP / store submission** | All data-subject rights (deletion, access, portability) fulfilled via `support@priority-guard.com` within 30 days per Art. 12(3). Satisfies OpenAI requirement #38 and GDPR. **No automation required at this tier.** | Current |
| **Tier 2 — automation, post-launch** | `delete_user_data(user_id)` Celery job, `delete_my_data` MCP tool, export endpoints, inactivity cleanup. Reduce operational burden; **explicitly NOT blockers for submission or compliance.** | In progress |

**Always active regardless of tier:** FK CASCADE, Redis TTL expiry, 7-day encrypted backups.

> The PG authenticated-deletion increment moves PG from Tier 1 to Tier 2. That is the source
> document's own roadmap, not a remediation.

---

## 5. Backups

Managed PostgreSQL with automated encrypted backups **retained 7 days**, then automatically and
permanently deleted. The source states this period is sufficient for operational recovery and
aligns with data minimisation.

**Deletion from active storage does not remove data from backups.** Backup expiry is the
mechanism. This must be disclosed accurately in the privacy policy; it is not something the
deletion code can or should act on.

*Verification note: Render's API exposes no backup-retention field for
`priority-guardian-db`; the 7-day figure is from the source document and unconfirmed against
the dashboard.*

---

## 6. Security measures (summary)

AES-256 at rest, TLS 1.3 in transit. Credential vault with MFA. One-person controller model, no
access sharing. Pseudonymisation (UUID rather than real identity). Role-based least-privilege
access with cloud audit logging. Automated deletion and verification logs (30 days).

---

## 7. Known conflicts — recorded, with decisions

The source predates ADR_008's Operation A / Operation B distinction. Two conflicts follow from
that, and both were decided 2026-08-01.

### 7.1 `oauth_sessions` — delete or retain?

| Source | Position |
|---|---|
| This document, §2 | *"Removed immediately when the user deletes their **account**"* |
| ADR_008 §1 | **Retained** on PG-scoped deletion — suite-level browser session, not PG state |

**Not actually a conflict once the two operations are distinguished.** The source describes
account deletion (Operation B). PG-scoped deletion (Operation A) is a narrower thing the source
did not contemplate.

**DECISION: retain `oauth_sessions` in `delete_my_priority_guardian_data`.** The session is
suite-level and a MindSort user would lose their session for a PG-scoped request. Delete them
in Operation B, where the source's rule applies. **ADR_008 §1 stands unchanged.**

### 7.2 Audit retention — 30 days or 90?

| Source | Value | Applies to |
|---|---|---|
| §2 retention table | **90 days** | `core_tool_audit_log` — tool execution audit |
| §3 deletion mechanism | **30 days** | *verification log* — a line written after deletion to prove it happened |
| `backend/core/models.py` | 90 days | `core_tool_audit_log` column comment |
| `backend/jobs/retention_cleanup.py` | **90 days** | `cleanup_expired_audit_logs`: `WHERE created_at < NOW() - INTERVAL '90 days'` |

**These are two different artefacts, not one figure stated twice.** The 90-day value governs the
operational audit log and is implemented. The 30-day value governs a deletion-verification
record.

**Finding: the 30-day verification log has no writer anywhere in the repository** (verified
2026-08-01). It is specified and unbuilt.

**DECISION: `core_tool_audit_log` retention is 90 days** — that is what the code does and what
the model documents. Do **not** merge the two. The 30-day verification log is either (a) defined
as a distinct record type and built, or (b) struck from the source as an unbuilt specification.
**Until resolved, the privacy policy must not claim a 30-day deletion-verification retention.**

*Open — requires a decision from Nadja, not from an implementing increment.*

---

## 8. Cross-references

- `doc/ADR_008_data_ownership_and_deletion_model.md` — ownership table, Operation A / B split
- `doc/ADR_007_user_identity_and_lifecycle.md` — identity model, pseudonymisation
- `doc/ADR_006_token_revocation_semantics.md` — disconnect vs deletion; residual access window
- `doc/legal/pg_privacy_policy_v3.1.md` — **stale**; the live policy at
  `https://www.fulfilling-productivity.com/pg-privacy-policy` is authoritative
- `backend/jobs/retention_cleanup.py` — implemented cleanup jobs
