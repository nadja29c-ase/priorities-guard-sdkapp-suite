Increment Briefing: GDPR Retention Enforcement — Missing Cleanup Jobs
Context
The privacy policy (v2.0) makes four promises currently not enforced by code, creating a policy–practice mismatch and storage limitation compliance risk:

Audit logs deleted after 90 days — rolling delete on core_tool_audit_log — no task exists
Inactive accounts anonymized/deleted after 6 months — no task exists
Google OAuth tokens revoked after 6 months inactivity — no task exists, and no reliable inactivity signal exists yet
Browser sessions cleaned up after 6-month inactivity — task cleanup_expired_oauth_sessions exists in backend/jobs/oauth_cleanup.py but is not registered in the beat schedule


Existing Patterns to Follow

backend/jobs/oauth_cleanup.py — canonical pattern for all new cleanup tasks: structlog, async-in-sync via get_event_loop, bind=True, max_retries=3, exponential retry backoff
backend/core/celery_app.py — beat schedule; all task registrations go here
backend/core/models.py — CoreUser, CoreConnection, CoreConsent, CoreToolAuditLog
backend/apps/priority_guardian/routers/offboarding_router.py — reference for account-level cascade deletion via core_users.id FK
backend/apps/priority_guardian/services/calendar_service.py — compute_time_allocation() is currently the only function performing real Google Calendar API calls (list_events, get_user_timezone). This is not a permanent assumption — see last_used_at contract below.
tests/integration/priority_guardian/test_db_integrity.py and tests/integration/focused/test_database.py — canonical patterns for DB integration tests: real PostgreSQL, async_session fixture, text() SQL, pytest.mark.asyncio


DB Migration Required
Migration: Add last_used_at and indexes to core_connections

New nullable DateTime(timezone=True) column last_used_at, no server default, no backfill
Add simple index: ix_core_connections_last_used_at on (last_used_at)
Add partial index for Task 2 query performance:

sql  CREATE INDEX ix_core_connections_google_active
  ON core_connections(last_used_at)
  WHERE connection_type = 'google' AND revoked_at IS NULL;
This keeps Task 2 O(log n) as the table grows. Without it, the monthly cleanup becomes a full table scan.

down_revision: y5z6a7b8c9d0 (current head)
Downgrade must drop both indexes and the column cleanly

Update backend/core/models.py: add last_used_at: Mapped[datetime | None] to CoreConnection with a comment documenting the architectural rule (see below).

last_used_at Update Contract
last_used_at means: "a real Google Calendar API call succeeded for this connection."
Rule: set connection.last_used_at = datetime.now(timezone.utc) immediately after each successful Google API response — not after all calls succeed together, not on token refresh, not on DB-only operations. Both get_user_timezone and list_events in compute_time_allocation() must independently update it on success. If get_user_timezone succeeds but list_events fails, the timestamp must still reflect the successful get_user_timezone call.
Transaction discipline: compute_time_allocation() operates within a request-scoped session passed in from the router. Set the field and let the existing transaction boundary commit it. Do not add an extra commit() mid-function.
Permanent architectural rule (enforced from this increment forward): any new Google Calendar API call anywhere in the codebase must update last_used_at on the relevant CoreConnection after a confirmed successful response. This applies to all apps in the suite. Document this rule as a comment on the last_used_at field in CoreConnection.
last_used_at starts as NULL for all existing connections. The cleanup task handles NULL via fallback to created_at (see Task 2).

Multi-App Guardrail (Known Limitation — Explicitly Deferred)
Task 3's deletion criteria rely on core_consents and core_connections being the authoritative activity signals across the suite. This is safe in the current single-app state.
Hard rule before any second app goes live: either implement core_users.last_active_at updated on every authenticated request (suite-wide middleware), OR enforce that all apps write core_consents rows for every active auth session. Without one of these, Task 3 can delete users that are active in a second app but have no consent or connection rows. This must be resolved as a named architecture increment before app 2 ships.

Fix 1: Register Existing Session Cleanup Task
cleanup_expired_oauth_sessions exists in backend/jobs/oauth_cleanup.py but is missing from the beat schedule. Beat schedule entry only — no code changes to the task itself.

New Tasks: backend/jobs/retention_cleanup.py (new file)
Follow the exact structure of oauth_cleanup.py.
Applies to all three tasks:

Use job_run_id = str(uuid4()) per task invocation as the structured log identifier — not correlation_id
All now values must use datetime.now(timezone.utc) — never datetime.utcnow() (naive) or datetime.now() (local time)
Log job_run_id, duration_ms, and deleted/affected count per task invocation
max_retries=3, exponential backoff on all tasks


Task 1: cleanup_expired_audit_logs

Delete rows from core_tool_audit_log where created_at < NOW() - INTERVAL '90 days'
Use an atomic CTE delete with RETURNING in a loop. PostgreSQL does not support DELETE … LIMIT directly. A two-step select-then-delete is not safe under concurrent workers. SQLAlchemy rowcount on CTEs is unreliable. Use a single atomic statement per iteration:

sql  WITH rows AS (
    SELECT id FROM core_tool_audit_log
    WHERE created_at < NOW() - INTERVAL '90 days'
    ORDER BY created_at
    LIMIT 500
  )
  DELETE FROM core_tool_audit_log
  WHERE id IN (SELECT id FROM rows)
  RETURNING id;
Loop until the RETURNING result set is empty. Loop termination is based on returned rows, not rowcount.

created_at is already indexed via idx_audit_log_created_at
Schedule: daily at 02:00 UTC

Task 2: cleanup_idle_google_connections

Target rows in core_connections where:

connection_type = 'google'
revoked_at IS NULL
last_used_at < NOW() - INTERVAL '6 months' OR (last_used_at IS NULL AND created_at < NOW() - INTERVAL '6 months')


The IS NULL fallback handles connections that pre-date this migration
Action: set revoked_at = datetime.now(timezone.utc) (soft revoke — mirrors disconnect pattern). Does NOT cascade-delete the user. Live calendar access is terminated; user data is retained.
Schedule: monthly, 1st of each month at 03:00 UTC

Task 3: cleanup_inactive_accounts

A core_users row qualifies for hard deletion when ALL of the following are true:

core_users.created_at < NOW() - INTERVAL '6 months'
No active Google connection: no row in core_connections where user_id = X AND revoked_at IS NULL
No active consent: no row in core_consents where user_id = X AND revoked_at IS NULL


Action: hard delete the core_users row. Existing ON DELETE CASCADE FKs propagate to: core_connections, core_consents, pg_priorities → pg_deliverables, pg_goals, pg_weekly_snapshots, OAuth sessions and tokens
Do NOT delete core_tool_audit_log rows — intentionally no FK to core_users; those rows expire independently via Task 1
Schedule: monthly, 1st of each month at 04:00 UTC — one hour after Task 2 so idle connections are soft-revoked before the inactivity check runs
Do not log individual user UUIDs — log count only


Beat Schedule Registration
Add to backend/core/celery_app.py beat_schedule:
Task nameTask pathScheduleQueueExpirescleanup-oauth-sessions-weeklybackend.jobs.oauth_cleanup.cleanup_expired_oauth_sessionsSunday 01:00 UTCfocused86400cleanup-audit-logs-dailybackend.jobs.retention_cleanup.cleanup_expired_audit_logsdaily 02:00 UTCfocused86400cleanup-idle-google-connections-monthlybackend.jobs.retention_cleanup.cleanup_idle_google_connections1st of month 03:00 UTCfocused604800cleanup-inactive-accounts-monthlybackend.jobs.retention_cleanup.cleanup_inactive_accounts1st of month 04:00 UTCfocused604800
Monthly tasks use expires=604800 (7 days) to survive worker downtime without silently skipping.

Unit Tests
File: tests/unit/celery/test_retention_cleanup.py
No real DB. Mock AsyncSessionLocal and assert correct SQL logic per task.
cleanup_expired_audit_logs

Atomic CTE with RETURNING is used — not a two-step select+delete
Loop exits when RETURNING result set is empty
Idempotent: running twice produces same result

cleanup_idle_google_connections

Connection with last_used_at > 6 months ago and revoked_at IS NULL gets revoked_at set
Connection with last_used_at IS NULL and created_at > 6 months ago gets revoked_at set (NULL fallback)
Connection with recent last_used_at is untouched
Already-revoked connections are untouched
Non-google connection_type rows are untouched
Idempotent

cleanup_inactive_accounts

User matching all three deletion criteria is deleted
User with active connection is retained
User with active consent is retained
User created less than 6 months ago is retained
Idempotent


DB Integration Tests
File: tests/integration/priority_guardian/test_retention_cleanup_db.py
Use real PostgreSQL. Follow the pattern in test_db_integrity.py and test_database.py: async_session fixture, text() SQL for setup where appropriate, pytest.mark.asyncio.
Migration integrity

After upgrade: last_used_at column exists on core_connections, is nullable, has no server default
After upgrade: both ix_core_connections_last_used_at and ix_core_connections_google_active indexes exist
After downgrade: column and both indexes removed cleanly
All pre-existing rows have last_used_at = NULL after migration (no backfill)

last_used_at update contract

After compute_time_allocation() completes with both API calls succeeding (mock both to return success): connection.last_used_at is set and persisted in DB
If get_user_timezone succeeds but list_events is mocked to fail: last_used_at reflects the get_user_timezone success — not NULL
On token-error path (before any API call): connection.last_used_at is NOT updated
No extra commit introduced: session committed exactly once at request boundary

cleanup_expired_audit_logs — DB behavior

Seed: 5 rows with created_at = 91 days ago, 3 rows with created_at = 30 days ago
Run cleanup function directly against real DB
Assert: 5 old rows deleted, 3 recent rows remain
Assert: loop terminates correctly on empty RETURNING result (no infinite loop)
Assert: RETURNING result set drives termination, not rowcount

cleanup_idle_google_connections — DB behavior

Seed: user A with last_used_at = 7 months ago, revoked_at NULL; user B with last_used_at = 1 week ago; user C with last_used_at NULL and created_at = 7 months ago; user D already revoked
Run cleanup function against real DB
Assert: user A and C get revoked_at set to a recent timezone.utc timestamp; user B and D untouched

cleanup_inactive_accounts — DB behavior

Seed: active user (recent connection + active consent), disconnected-but-consented user, fully inactive user (created_at = 7 months ago, no active connection, no active consent) with associated pg_priorities, pg_goals, pg_weekly_snapshots
Seed a core_tool_audit_log row referencing the inactive user's UUID
Run Task 2 then Task 3 in sequence against real DB
Assert: only the fully inactive user's core_users row is deleted
Assert: cascade verified — inactive user's pg_priorities, pg_goals, pg_weekly_snapshots no longer exist
Assert: core_tool_audit_log row referencing the deleted user UUID still exists (audit log independence)
Assert: active and disconnected-but-consented users are fully intact


Pre-Deploy
Before committing: read OPERATIONS_PREDEPLOYMENT.md and check for additional pre-deploy tasks.
This increment includes a DB migration. Run against staging before deploying to production.