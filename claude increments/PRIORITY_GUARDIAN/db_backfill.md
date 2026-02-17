# Briefing: DB-Level Integration Test Backfill

## Context

All existing integration tests verify behavior via API responses. The actual database state after operations has never been verified against real PostgreSQL. This means DB constraints, CASCADE behavior, and post-operation state are trusted but unproven. This briefing covers the gaps.

**File location:** `tests/integration/priority_guardian/test_db_integrity.py`

**Uses real test PostgreSQL** — no mocks on the DB layer. Use the existing `async_session` and `client` fixtures from conftest.

**Important:** Some existing snapshot tests in `test_snapshot_persistence.py` reference `desired_result` on `PgPriority`, which was removed in Increment D (replaced by `pg_goals`). Check whether `PgPriority.__init__` silently ignores this kwarg or if those tests are broken. If broken, fix them (remove `desired_result=` from the test fixtures). If SQLAlchemy silently ignores it, still remove it for correctness.

---

## Test Categories

### 1. CASCADE DELETE Verification

**What:** Verify that deleting a priority via the API actually removes child rows from the database (not just from the API response).

**Setup helper:** Create a user, a priority, then attach deliverables, goals, and snapshots directly via ORM/SQL.

**Tests:**

1a. **Delete priority cascades deliverables in DB**
- Create deadline priority with 2 deliverables
- DELETE priority via API
- `SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :id` → assert 0

1b. **Delete priority cascades goals in DB**
- Create flexible priority with 2 goals
- DELETE priority via API
- `SELECT COUNT(*) FROM pg_goals WHERE priority_id = :id` → assert 0

1c. **Delete priority cascades snapshots in DB**
- Create flexible priority
- Insert 2 snapshot rows directly via SQL (use valid week_start Mondays, week_end = week_start + 6)
- DELETE priority via API
- `SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :id` → assert 0

1d. **Delete priority does NOT cascade other users' data**
- Create user A with priority + deliverable
- Create user B with priority + deliverable
- DELETE user A's priority
- Verify user B's deliverable still exists in DB

1e. **Delete retired priority cascades children in DB**
- Create flexible priority with goals and snapshots
- Retire the priority (set status='retired', retired_at=NOW() via API or direct SQL)
- DELETE the retired priority via API
- `SELECT COUNT(*) FROM pg_goals WHERE priority_id = :id` → assert 0
- `SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :id` → assert 0
- Proves FK CASCADE works regardless of priority status (not dependent on partial index)

---

### 2. Partial Unique Index Enforcement

**What:** Verify `idx_pg_priorities_user_keyword_active` actually rejects duplicates at the PostgreSQL level.

**Tests:**

2a. **Duplicate active keyword rejected by real index**
- Create user
- Insert priority with P1 + status='active' directly via ORM
- Attempt second INSERT with same user_id, P1, status='active'
- Assert raises `IntegrityError` (not caught by application — raw insert)

2b. **Same keyword allowed when one is retired**
- Create user
- Insert priority with P1 + status='retired' directly via ORM
- Insert second priority with P1 + status='active'
- Assert succeeds (partial index only covers active)

2c. **Different users can have same active keyword**
- Create user A and user B
- Insert P1 active for user A, P1 active for user B
- Assert both succeed (index is per-user)

2d. **Reactivating retired priority with duplicate keyword rejected**
- Create user
- Insert priority A with P1 + status='active'
- Insert priority B with P1 + status='retired' + retired_at set (allowed by partial index)
- `UPDATE pg_priorities SET status='active', retired_at=NULL WHERE id = :b_id`
- Assert raises IntegrityError (partial index now covers both rows)
- This tests the index on UPDATE, not just INSERT — critical for reactivation scenarios

---

### 3. CHECK Constraint Enforcement

**What:** Verify CHECK constraints actually reject invalid data at the PostgreSQL level. Use raw SQL INSERT to bypass application validation.

**Tests:**

3a. **Invalid calendar_keyword rejected**
- `INSERT INTO pg_priorities (..., calendar_keyword='P4', ...)` → assert raises IntegrityError mentioning `ck_pg_priorities_keyword`

3b. **Invalid type rejected**
- `INSERT INTO pg_priorities (..., type='invalid', ...)` → assert raises IntegrityError mentioning `ck_pg_priorities_type`

3c. **Invalid status rejected**
- `INSERT INTO pg_priorities (..., status='unknown', ...)` → assert raises IntegrityError mentioning `ck_pg_priorities_status`

3d. **Type-field consistency: deadline with weekly_hour_target rejected**
- `INSERT INTO pg_priorities (type='deadline', deadline=..., weekly_hour_target=10, ...)` → assert raises IntegrityError mentioning `ck_pg_priorities_type_field_consistency`

3e. **Type-field consistency: flexible with deadline rejected**
- `INSERT INTO pg_priorities (type='flexible', weekly_hour_target=10, checkpoint_date=..., deadline=..., ...)` → assert raises IntegrityError

3f. **Negative weekly_hour_target rejected**
- `INSERT INTO pg_priorities (type='flexible', weekly_hour_target=-5, ...)` → assert raises IntegrityError mentioning `ck_pg_priorities_weekly_target_positive`

3g. **Retirement consistency: active with retired_at rejected**
- `INSERT INTO pg_priorities (status='active', retired_at=NOW(), ...)` → assert raises IntegrityError mentioning `ck_pg_priorities_retirement_consistency`

3h. **Retirement consistency: retired without retired_at rejected**
- `INSERT INTO pg_priorities (status='retired', retired_at=NULL, ...)` → assert raises IntegrityError

3i. **Snapshot: negative actual_hours rejected**
- `INSERT INTO pg_weekly_snapshots (actual_hours=-1, ...)` → assert raises IntegrityError mentioning `ck_pg_weekly_snapshots_actual_hours_non_negative`

3j. **Snapshot: week_end != week_start + 6 rejected**
- `INSERT INTO pg_weekly_snapshots (week_start='2026-02-02', week_end='2026-02-10', ...)` → assert raises IntegrityError mentioning `ck_pg_weekly_snapshots_week_consistency`

3k. **Snapshot: week_start not Monday rejected**
- `INSERT INTO pg_weekly_snapshots (week_start='2026-02-03', week_end='2026-02-09', ...)` → (Tuesday) assert raises IntegrityError mentioning `ck_pg_weekly_snapshots_week_start_monday`

**Note for all CHECK constraint tests:** Use raw `session.execute(text("INSERT INTO ..."))` to bypass ORM/Pydantic validation. The point is proving PostgreSQL rejects the data, not that the application rejects it. Wrap each in `pytest.raises(IntegrityError)` and rollback after.

3l. **CHECK constraint enforced on UPDATE (representative test)**
- Insert a valid flexible priority via ORM
- `UPDATE pg_priorities SET type='invalid' WHERE id = :id` via raw SQL
- Assert raises IntegrityError mentioning `ck_pg_priorities_type`
- Proves CHECK fires on UPDATE, not just INSERT

---

### 4. Foreign Key Constraint Existence

**What:** Verify FK constraints are real and enforced at the PostgreSQL level, not just declared in the ORM.

**Tests:**

4a. **Deliverable with non-existent priority_id rejected**
- `INSERT INTO pg_deliverables (id, priority_id, name, done) VALUES (gen_random_uuid(), gen_random_uuid(), 'Test', false)`
- Assert raises IntegrityError (FK violation)

4b. **Goal with non-existent priority_id rejected**
- `INSERT INTO pg_goals (id, priority_id, text, achieved) VALUES (gen_random_uuid(), gen_random_uuid(), 'Test', false)`
- Assert raises IntegrityError (FK violation)

4c. **Snapshot with non-existent priority_id rejected**
- `INSERT INTO pg_weekly_snapshots (id, priority_id, user_id, week_start, week_end, actual_hours) VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), '2026-02-02', '2026-02-08', 5.0)`
- Assert raises IntegrityError (FK violation)

---

### 5. Offboarding DB State Verification

**What:** Verify the disconnect endpoint actually modifies DB state, not just returns the right response.

**Setup:** Create user with Google connection (use existing `pg_user_with_connection` fixture pattern from `test_pg_offboarding.py`). Mock Google revoke API (same as existing tests).

**Tests:**

5a. **Disconnect sets revoked_at on connection**
- POST /disconnect
- `SELECT revoked_at FROM core_connections WHERE user_id = :id AND provider = 'google'` → assert NOT NULL

5b. **Disconnect revokes PG OAuth tokens**
- Create OAuth access token with scope containing 'pg.access', revoked=False
- POST /disconnect
- `SELECT revoked FROM oauth_access_tokens WHERE user_id = :id AND 'pg.access' = ANY(scope)` → assert True

5c. **Disconnect preserves priority data**
- Create user with priorities and deliverables
- POST /disconnect
- `SELECT COUNT(*) FROM pg_priorities WHERE user_id = :id` → assert unchanged (data NOT deleted)

5d. **Disconnect preserves snapshots**
- Create user with priorities and snapshots
- POST /disconnect
- `SELECT COUNT(*) FROM pg_weekly_snapshots WHERE user_id = :id` → assert unchanged
- Catches accidental cascade from connection FK to snapshot data

5e. **Double disconnect is idempotent in DB**
- POST /disconnect twice
- Second response returns `already_disconnected: true`
- DB state unchanged between first and second call (no duplicate revocations)

---

### 6. Fix Existing Snapshot Test Fixtures

**What:** `test_snapshot_persistence.py` real-DB tests reference `desired_result` on `PgPriority`, which was removed in Increment D.

**Action:**
- Check `TestRealDBUniqueConstraint`, `TestRealDBSumBasedAggregates`, `TestRealDBIdempotentAggregates`, `TestRealDBZeroHours` classes
- Remove `desired_result="Test result"` from all `PgPriority()` constructor calls in these test classes
- Run the real-DB tests and confirm they pass

---

### 6. Transaction Rollback State Verification

**What:** Verify that after an IntegrityError and rollback, the DB state is unchanged — no partial writes leaked.

**Test:**

6a. **Rollback after IntegrityError preserves existing data**
- Create user
- Insert priority with P1 + status='active' via ORM, flush + commit
- Begin new operation: attempt raw INSERT of duplicate P1 active for same user
- Assert raises `IntegrityError`
- Rollback session
- Query DB: original priority row still exists with correct data (id, name, keyword, status all unchanged)
- Query DB: exactly 1 row for this user in `pg_priorities` (no partial second row)

---

## Implementation Notes

- Use `pytest.raises(IntegrityError)` for constraint tests, and `await session.rollback()` after each to reset state. This is critical — without rollback, the session enters an invalid state and subsequent tests fail with `InvalidRequestError: Can't reconnect until invalid transaction is rolled back`.
- For CASCADE tests, query the DB directly via `session.execute(text("SELECT ..."))` — don't rely on ORM relationships
- Use raw SQL INSERT for CHECK constraint tests to bypass application-level validation
- All tests in this file use the real test PostgreSQL instance (no mocking the DB layer)
- Group tests by category using test classes: `TestCascadeDelete`, `TestPartialUniqueIndex`, `TestCheckConstraints`, `TestForeignKeyConstraints`, `TestOffboardingDBState`

## Unit Tests

N/A — this is entirely integration tests against real PostgreSQL.

## Acceptance Criteria

- [ ] CASCADE delete verified for deliverables, goals, and snapshots at DB level
- [ ] CASCADE delete verified for retired priorities (status-independent)
- [ ] Partial unique index proven to reject duplicate active keywords on INSERT
- [ ] Partial unique index proven to reject duplicate active keywords on UPDATE (reactivation)
- [ ] Partial unique index proven to allow same keyword for retired + active
- [ ] All CHECK constraints exercised with invalid data via raw SQL INSERT
- [ ] At least one CHECK constraint exercised on UPDATE
- [ ] FK constraints proven to reject orphaned child rows (deliverables, goals, snapshots)
- [ ] Offboarding DB state verified (revoked_at, token revocation, data + snapshot preservation)
- [ ] `desired_result` removed from existing snapshot test fixtures
- [ ] Transaction rollback proven to preserve existing data after IntegrityError
- [ ] All existing tests still pass
- [ ] All new tests pass against real test PostgreSQL
