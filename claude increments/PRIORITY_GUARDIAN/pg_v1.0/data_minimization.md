# Data Minimization — GDPR Art. 5(1)(c) Compliance

## Context

Codebase audit (2026-03-03) identified five data minimization issues across the shared backend and PG app. One is high severity (data flowing over the network that PG never uses), the rest are low-to-medium dead columns and unused writes.

This increment is **shared architecture scope** — changes touch `core/google_calendar.py`, `core/oauth_provider/models.py`, `core/oauth_provider/services/`, `apps/clarity/db_models.py`, and their respective tests.

**GDPR principle at stake:** Art. 5(1)(c) — "Personal data shall be adequate, relevant and limited to what is necessary."

---

## Change 1: Google Calendar API Field Filtering (HIGH)

### Problem

`fetch_events()` and `list_events()` in `backend/core/google_calendar.py` do NOT specify a `fields` parameter. Google Calendar API returns ALL event fields by default. PG receives fields it never reads or processes: `location`, `creator` (contains email), `organizer` (contains email), `attendees[].email`, `attachments`, `conferenceData`, `reminders`, `colorId`, `htmlLink`, `hangoutLink`, `recurringEventId`, `transparency`, `visibility`, `iCalUID`, `sequence`, `extendedProperties`, etc.

Some of these contain personal data (organizer email, creator email, full attendee email list). PG discards them after processing, but they still transit the network from Google to PG backend (EU).

### Fields PG actually uses

Verified across both code paths:

| Field | Used by | Purpose |
|---|---|---|
| `id` | `compute_allocation_from_events()` | Deduplication via `seen_event_ids` set |
| `summary` | `match_keywords()` + `process_events_for_report()` | P1/P2/P3 keyword matching + LLM semantic grouping |
| `description` | `process_events_for_report()` | LLM semantic grouping (current week only) |
| `start.dateTime` | `compute_event_duration_hours()` | Duration computation |
| `start.date` | `is_all_day_event()` | All-day event detection (to exclude) |
| `end.dateTime` | `compute_event_duration_hours()` | Duration computation |
| `end.date` | (implicit — returned alongside `end.dateTime`) | Part of event structure |
| `status` | `is_cancelled_event()` | Filter cancelled events |
| `attendees` | `is_declined_event()` | Only reads `self` + `responseStatus` per attendee |

### What to change

Add a `fields` query parameter to the `params` dict in both `fetch_events()` and `list_events()`.

**For `fetch_events()`:**

The `params` dict currently has: `timeMin`, `timeMax`, `maxResults`, `singleEvents`, `orderBy`.

Add one key: `"fields"` with value `"items(id,summary,description,start,end,status,attendees(self,responseStatus))"`

**For `list_events()`:**

The `base_params` dict currently has: `timeMin`, `timeMax`, `maxResults`, `singleEvents`, `orderBy`.

Add one key: `"fields"` with value `"items(id,summary,description,start,end,status,attendees(self,responseStatus)),nextPageToken"`

Note: `list_events` needs `nextPageToken` at the top level because it paginates via `data.get("nextPageToken")`.

### What NOT to change

- No changes to `get_user_timezone()` (different API endpoint, no event data)
- No changes to `register_webhook()` or `stop_webhook_channel()` (different API endpoints)
- No changes to any service or MCP tool code — they already read only the fields listed above
- No changes to Focused's usage of these functions (Focused also only uses a subset of fields)

### Backward compatibility

The `fields` parameter is additive — Google returns fewer fields, not different ones. All downstream code already accesses only the fields listed above. The existing `event.get("summary", "")` / `event.get("description", "")` patterns will continue to work identically.

---

## Change 2: Drop `last_used_at` from `OAuthAccessToken` (LOW)

### Problem

`OAuthAccessToken.last_used_at` is set to `datetime.now(timezone.utc)` on token creation and refresh in `token_service.py` (both `exchange_authorization_code` and `exchange_refresh_token`). But it is:

- Never updated on actual token usage (JWT validation in `mcp_auth.py` is stateless — no DB write)
- Never queried by any service, cleanup job, or admin endpoint
- Never used in any WHERE clause, ORDER BY, or analytics

It is a write-only column that records creation time (duplicating `created_at`).

### What to change

1. Create an Alembic migration that drops `last_used_at` from `oauth_access_tokens`
2. Remove the `last_used_at` column definition from `OAuthAccessToken` in `backend/core/oauth_provider/models.py`
3. Remove `last_used_at=datetime.now(timezone.utc)` from both `OAuthAccessToken(...)` constructors in `token_service.py` (in `exchange_authorization_code` and `exchange_refresh_token`)

### What NOT to change

- No changes to `mcp_auth.py`
- No changes to cleanup jobs
- No changes to any test that does not directly reference `last_used_at`

---

## Change 3: Drop `session_token` Plaintext from `OAuthSession` (MEDIUM)

### Problem

`OAuthSession` has three token columns:
- `session_token` — plaintext (Phase 1, deprecated per code comment)
- `session_token_hash` — SHA-256 hash (used for O(1) indexed lookup)
- `session_token_enc` — Fernet-encrypted (for audit/recovery)

`session_service.py` currently uses `session_token_hash` for primary lookup and falls back to `session_token` for "legacy sessions (pre-migration)." The plaintext column stores a secret in cleartext in PostgreSQL.

### Pre-condition check

Before dropping, verify there are no sessions with `session_token_hash IS NULL`. If any exist, they are pre-Phase-1 legacy rows that would lose their only lookup path.

### What to change

1. Create an Alembic migration:
   - First: `UPDATE oauth_sessions SET session_token_hash = encode(digest(session_token, 'sha256'), 'hex') WHERE session_token_hash IS NULL` (backfill any legacy rows)
   - Then: Drop the `session_token` column
   - Then: Drop the `idx_oauth_sessions_session_token` index (unique index on the dropped column)
   - Then: Make `session_token_hash` NOT NULL (it was nullable for Phase 1 transition)

2. Remove `session_token` from `OAuthSession` model in `backend/core/oauth_provider/models.py`

3. Remove the `idx_oauth_sessions_session_token` index definition from `__table_args__`

4. In `session_service.py`:
   - `create_session()`: Remove `session_token=session_token` from the `OAuthSession(...)` constructor
   - `get_session_user()`: Remove the entire "Fallback to plaintext lookup" block (the `if not session:` block after the hash lookup)
   - `delete_session()`: Remove the entire "Fallback to plaintext delete" block

### Important: `session_token_enc` stays

`session_token_enc` (Fernet-encrypted) is retained for audit/recovery. Only the plaintext column is dropped.

---

## Change 4: Drop Deprecated Clarity Columns (LOW)

### Problem

`ClarityCluster` in `backend/apps/clarity/db_models.py` has two deprecated columns:

- `thoughts_exhausted`: Boolean, always set to `False` on new saves. Deprecated per code comment: "DEPRECATED: Always false in explicit save model."
- `correctly_clustered`: Boolean nullable, always set to `None` on new saves. Deprecated per code comment: "DEPRECATED: User confirmation. Always null in explicit save model."

Both were part of the original Clarity flow before Increment 12 switched to explicit save model. They carry no data.

### What to change

1. Create an Alembic migration that drops both columns from `clarity_clusters`
2. Remove both column definitions from `ClarityCluster` in `backend/apps/clarity/db_models.py`
3. Remove `thoughts_exhausted` and `correctly_clustered` from the Example in the class docstring
4. Update any test that sets or asserts on these fields

### What NOT to change

- `content_hash` stays (actively used for saved-state detection)
- The `idx_clarity_clusters_user_created` index stays (documented as "can be dropped in future cleanup" but is a separate concern)

---

## Change 5: Drop `nonce` from `OAuthAuthorizationCode` (LOW)

### Problem

`OAuthAuthorizationCode.nonce` is an OpenID Connect field. The suite does not implement OpenID Connect. The column is nullable and always NULL. No code writes to it; no code reads from it.

### What to change

1. Create an Alembic migration that drops `nonce` from `oauth_authorization_codes`
2. Remove the `nonce` column definition from `OAuthAuthorizationCode` in `backend/core/oauth_provider/models.py`

---

## Migration strategy

All column drops (Changes 2–5) go in a **single Alembic migration**. Change 1 is code-only (no migration).

The migration should:

1. Backfill `session_token_hash` for any NULL rows (Change 3 pre-condition)
2. Drop `last_used_at` from `oauth_access_tokens`
3. Drop `session_token` from `oauth_sessions` + drop its unique index
4. Make `session_token_hash` NOT NULL on `oauth_sessions`
5. Drop `thoughts_exhausted` and `correctly_clustered` from `clarity_clusters`
6. Drop `nonce` from `oauth_authorization_codes`

Name: `data_minimization_cleanup`

---

## Unit Tests

### Change 1: Google API fields parameter

- Test that `fetch_events()` includes `fields` key in params with the correct value
- Test that `list_events()` includes `fields` key in `base_params` with the correct value (must include `nextPageToken`)
- Test that mock events containing only the specified fields still produce correct output from `compute_allocation_from_events()` and `process_events_for_report()`
- Test that events missing previously-received-but-unused fields (e.g., no `location`, no `creator`) do not cause KeyError or behavior change

### Change 2: `last_used_at` removal

- Test that `exchange_authorization_code` returns valid token response without setting `last_used_at`
- Test that `exchange_refresh_token` returns valid token response without setting `last_used_at`

### Change 3: `session_token` plaintext removal

- Test that `create_session` creates session without `session_token` column
- Test that `get_session_user` finds session by hash only (no fallback path)
- Test that `delete_session` deletes by hash only (no fallback path)

### Change 4: Clarity deprecated columns

- Test that `ClarityCluster` model can be instantiated without `thoughts_exhausted` and `correctly_clustered`
- Update any existing test fixtures that set these fields

### Change 5: `nonce` removal

- Test that `OAuthAuthorizationCode` model can be instantiated without `nonce`

---

## Integration Tests

### Change 1: Google API fields parameter

- Integration test that mocks the Google Calendar API response with ONLY the fields specified in the `fields` parameter and verifies the full pipeline (`compute_time_allocation` and `generate_weekly_report`) produces correct results
- The mock response must be shaped like what Google returns when `fields` is set (no `location`, `creator`, `organizer`, `attachments`, etc.)

### Change 3: `session_token` removal

- Integration test: full session lifecycle (create, lookup, extend, delete) using hash-only path
- Integration test: ensure no SQL errors when `session_token` column is absent

### DB integrity tests (all changes)

After migration runs, verify:
- `oauth_access_tokens` has no `last_used_at` column
- `oauth_sessions` has no `session_token` column
- `oauth_sessions.session_token_hash` is NOT NULL
- `clarity_clusters` has no `thoughts_exhausted` or `correctly_clustered` columns
- `oauth_authorization_codes` has no `nonce` column
- All existing data is preserved (row counts unchanged)
- All indexes on remaining columns still exist

---

## Before deployment

- Read OPERATIONS.md (if it exists) and check for additional pre-deploy tasks
- Run full test suite after migration
- Verify no Alembic migration conflicts with pending branches
