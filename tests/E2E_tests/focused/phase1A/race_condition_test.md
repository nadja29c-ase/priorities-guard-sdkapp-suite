Race Condition Test — Spec for Claude Code
Test Name

test_12_race_condition_webhook_during_active_sync

Purpose

Verify that:

Webhook arrives → needs_sync = 1

Sync engine starts running and is mid-flight

Another webhook arrives DURING the sync

needs_sync MUST remain = 1 (not swallowed)

After sync completes, another sync MUST run

This ensures no focus events are lost when events change while a sync is running.

System Behavior Under Test
Redis Keys

needs_sync:{user_id}

sync_lock:{user_id}

Sync Engine (increment 1A)

Reads needs_sync

Clears it ONLY after successful sync

Uses sync_lock to prevent concurrent syncs

Does NOT swallow additional webhook-triggered sync requests

Webhook Processor

ALWAYS sets needs_sync = 1

Test Setup
1. Create fake user + connection

Use existing fixture: test_user_with_connection

2. Patch sync method so it:

Sleeps or yields mid-sync

Allows injecting a second webhook while lock is held

Allows tracking how many times sync was actually run

run_sync should be patched using patch("backend.apps.focused.logic_sync.run_sync")

3. Use real Redis test instance (fakeredis or test container)

Needs atomic key behavior.

Test Steps
Step 1: Trigger initial webhook
await process_webhook_event(... user_id ...)


Assert:

redis.get("needs_sync:{user_id}") == "1"

Step 2: Start sync in background and hold mid-flight

Use an async Task:

sync_task = asyncio.create_task(run_sync_job(user_id))
await wait_until(sync_lock is acquired)


Assert:

redis.exists("sync_lock:{user_id}") == True

Step 3: Fire second webhook DURING sync
await process_webhook_event(... user_id ...)


Assert:

redis.get("needs_sync:{user_id}") == "1"


(MUST NOT be cleared by sync engine prematurely.)

Step 4: Let sync finish
run_sync side effect releases lock and returns
await sync_task

Step 5: Sync engine must run AGAIN because needs_sync=1

Depending on your scheduler design:

Triggered automatically OR explicitly call run_sync_job(user_id) again.

Verify:

run_sync was called twice

The second run happens because the second webhook occurred mid-sync

Assertions
A. needs_sync Behavior
# After first webhook
needs_sync == 1  

# During sync (after second webhook)
needs_sync == 1  

# After sync completes
needs_sync == 0   (after second sync run)

B. Sync Run Count

mock_run_sync.call_count == 2

C. Lock Behavior
During sync: redis.exists(sync_lock) == True
After sync: redis.exists(sync_lock) == False

D. No swallowed webhook

The second webhook MUST trigger a second sync run.

Mocking Requirements
run_sync must:

Acquire sync_lock at start

Sleep/yield mid-sync (simulate multi-step)

Release lock on return

Ideal implementation:

async def fake_run_sync(user_id, *_):
    redis.set("sync_lock", 1)
    await asyncio.sleep(0.1)    # give room for the second webhook
    redis.delete("sync_lock")

Expected Claude Code Output

Claude Code should generate:

A new test function in test_increment_1a.py

Uses:

pytest.mark.asyncio

fakeredis or Redis test fixture

patch run_sync

async sleep or event to simulate mid-flight

Deterministic timing

Complete assertions above