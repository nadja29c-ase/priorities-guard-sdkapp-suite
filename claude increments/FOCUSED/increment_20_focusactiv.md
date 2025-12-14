# Increment #20: Focus Block Activation Scheduler

## Objective
Connect the sync pipeline to automatic Focus Mode activation. When a focus block is detected during sync, schedule a Celery task to trigger activation at the appropriate time.

## Trigger Flow
```
Webhook → needs_sync → sync_calendar_events() → focus block detected
    → schedule activation task for (start_time - lead_time)
    → task fires → generates shortcut URL → marks job 'pending_notification'
    → (Increment 21) notify_user sends push → user taps → Focus ON
```

## Context

**Existing Infrastructure:**
- `focused_focus_sessions` table stores synced events with `is_focus_block` flag
- `run_focus_mode` tool exists (Increment 11) with activation/deactivation logic
- `auto_deactivate_focus` Celery task pattern exists (Increment 11)
- Sync pipeline in `logic_sync.py` processes events via `process_single_event()`

**Tables Not Yet Created (needed for this increment):**
- `focused_scheduled_jobs` — defined in architecture, tracks pending Celery tasks
- `focused_consent_preferences` — stores `auto_handle_focus_blocks` boolean

---

## Requirements

### 1. Database Tables
Create migrations for:

**`focused_scheduled_jobs`:**
- `id` (UUID, PK)
- `user_id` (FK to core_users)
- `job_type` (enum: 'activation', 'deactivation')
- `event_id` (FK to focused_focus_sessions)
- `event_start_time` (timestamp — the actual event start time from calendar)
- `scheduled_at` (timestamp — when task should fire, computed as `event_start_time - lead_time`)
- `status` (enum: 'pending', 'running', 'pending_notification', 'pending_confirmation', 'completed', 'failed', 'cancelled', 'skipped')
- `celery_task_id` (string — for revocation)
- `shortcut_url` (string, nullable — generated URL for notification delivery)
- `retry_count` (int, default 0)
- `error_reason` (string, nullable)
- `created_at`, `updated_at`

**Status meanings:**
- `pending` — waiting for Celery to fire
- `running` — task executing
- `pending_notification` — URL generated, awaiting notify_user (Increment 21)
- `pending_confirmation` — user has auto=false, must initiate via ChatGPT
- `completed` — user tapped notification, Focus Mode activated
- `failed` — error during processing
- `cancelled` — event deleted/changed before firing
- `skipped` — user already had active focus session

**Unique constraint:** `(user_id, event_id, job_type, event_start_time)` — enforces idempotency

**Note:** Storing `event_start_time` separately allows lead_time changes without rescheduling existing jobs.

**`focused_consent_preferences`:**
- `user_id` (FK, unique)
- `auto_handle_focus_blocks` (boolean, default false) — if true: send push notification automatically when focus block starts; if false: user must initiate via ChatGPT
- `always_confirm_duration` (boolean, default true)
- `created_at`, `updated_at`

**Note:** `auto_handle_focus_blocks = true` means "send notification automatically", NOT "activate Focus Mode without user interaction" (iOS prevents that).

---

### 2. Scheduling Logic (integrated into sync)

When `process_single_event()` detects a new/updated focus block with `start_time` in the future:

```python
LEAD_TIME_MINUTES = 10  # configurable constant

# 1. Create DB row first (idempotency via unique constraint)
try:
    job = create_scheduled_job(
        user_id=user_id,
        event_id=session.id,
        job_type='activation',
        event_start_time=start_time,
        scheduled_at=start_time - timedelta(minutes=LEAD_TIME_MINUTES),
        status='pending'
    )
except IntegrityError:
    # Already scheduled for this event/time — skip
    return

# 2. Schedule Celery task with job.id
# Note: Using send_task() by name avoids circular imports
if start_time <= now + timedelta(minutes=LEAD_TIME_MINUTES):
    # Trigger immediately (no delayed ETA)
    task = celery_app.send_task(
        "backend.core.celery_app.trigger_focus_activation",
        args=[str(user_id), str(session.id), str(job.id)],
        queue="focused",
    )
else:
    # Schedule for start_time - lead_time
    eta = start_time - timedelta(minutes=LEAD_TIME_MINUTES)
    task = celery_app.send_task(
        "backend.core.celery_app.trigger_focus_activation",
        args=[str(user_id), str(session.id), str(job.id)],
        eta=eta,
        queue="focused",
    )

# 3. Update job with celery_task_id
job.celery_task_id = task.id
db.commit()
```

**Idempotency:** 
- DB unique constraint on `(user_id, event_id, job_type, event_start_time)`
- Catch `IntegrityError` → already scheduled, skip
- No Redis key needed

---

### 3. Celery Task: `trigger_focus_activation`

**Critical architecture note:** iOS does not allow remote Shortcut execution. The task's job is **timing + queueing for notification**, not direct Focus Mode activation. User must tap push notification to trigger Shortcut.

Flow: `Task fires → generates shortcut URL → queues notification → user taps → Focus ON`

**Critical:** This task calls backend Python functions directly. It does NOT call MCP tools. MCP is strictly for ChatGPT → Backend path.

```python
@celery.task(bind=True)
def trigger_focus_activation(self, user_id, session_id, job_id):
    # 1. Update job status to 'running'
    # 2. Re-fetch session from DB
    #    - If deleted or not is_focus_block → mark job 'cancelled', return
    # 3. Check user has active focus session (Increment 11 rule)
    #    - If yes → mark job 'skipped', return
    # 4. Generate shortcut URL via run_focus_mode_internal()
    #    - Store shortcut_url in job record (new column)
    # 5. Load consent preference (auto_handle_focus_blocks)
    #    - If True → mark job 'pending_notification' (notify_user delivers in Increment 21)
    #    - If False → mark job 'pending_confirmation' (user must initiate via ChatGPT)
    # 6. Handle errors:
    #    - URL generation failed → mark job 'failed', log error_reason
```

**Internal function:** Create `run_focus_mode_internal(user_id, ...)` that generates shortcut URL without MCP/HTTP overhead. Returns `{ shortcut_url, focus_name, end_time }`.

**New column on `focused_scheduled_jobs`:** `shortcut_url` (string, nullable) — stores generated URL for notification delivery.

---

### 4. Event Change Handling + Cancellation

When sync detects event changes:

**Event time changed:**
1. Look up existing job by `(user_id, event_id, job_type='activation')`
2. If `status = 'pending'`:
   - Call `celery.control.revoke(celery_task_id, terminate=False)`
   - Update job `status = 'cancelled'`
3. Schedule new job with new time

**Event deleted (soft-delete) or keywords removed:**
1. Look up existing job
2. If `status = 'pending'`:
   - Call `celery.control.revoke(celery_task_id, terminate=False)`
   - Update job `status = 'cancelled'`

**Do NOT revoke if status = 'running'** — let it complete and check event status internally.

---

### 5. Edge Cases
- Focus block already passed (`start_time < now`): Skip scheduling entirely
- User has active focus session: Task checks this at runtime, marks job 'skipped'
- Event deleted between scheduling and firing: Task re-checks, marks job 'cancelled'
- URL generation failed: Mark job 'failed', log `error_reason`
- User has no Google connection: Mark job 'failed' (shouldn't happen if sync created the event)

---

## Out of Scope
- `notify_user` implementation (Increment 21 — will consume `pending_notification` jobs)
- Push notification infrastructure (Increment 21)
- User timezone UI (verify sync stores UTC; no new logic needed)
- Multiple calendar support (still "primary" only)
- UI for managing `auto_handle_focus_blocks` preference
- Marking job `completed` (requires feedback that user tapped notification — Increment 21+)

---

## Test Coverage

**Unit:**
- Scheduling logic: new focus block creates job with status 'pending'
- Idempotency: duplicate insert raises IntegrityError, handled gracefully
- Immediate trigger: start_time within lead_time triggers immediately
- Skip past events: start_time in past → no job created
- Cancellation: event time change revokes old task, schedules new

**Integration:**
- Full flow: webhook → sync → job created → task fires → status becomes 'pending_notification'
- Event deletion: job cancelled before firing
- Active session guard: task skips if user already in focus mode, status 'skipped'
- Consent preference: auto=true → 'pending_notification'; auto=false → 'pending_confirmation'
- Shortcut URL generation: URL stored in job record

---

## Success Criteria
1. Focus blocks detected during sync automatically schedule activation tasks
2. Tasks fire at correct time (start_time - 10 min)
3. Tasks generate shortcut URL and mark job `pending_notification` or `pending_confirmation`
4. Event changes/deletions properly cancel/reschedule via `celery.control.revoke()`
5. Jobs tracked in `focused_scheduled_jobs` with correct status transitions
6. Idempotency enforced via DB unique constraint
7. Existing deactivation scheduling (Increment 11) continues working

**What Increment 20 delivers:** Correctly timed scheduler that prepares everything for notification delivery.

**What Increment 21 delivers:** `notify_user` implementation that consumes `pending_notification` jobs and sends push notifications.

---

## Dependencies
- Increment 11: `run_focus_mode` tool logic (extract to internal function)
- Increment 6B: Sync pipeline, `process_single_event()`
- Celery + Redis infrastructure

## Data Retention
- `focused_scheduled_jobs`: Completed/failed/cancelled jobs retained 7 days (existing cleanup pattern)
- `focused_consent_preferences`: Persistent until user deletion