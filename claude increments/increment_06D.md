Increment 6D — Sync Conflict Detection (MVP Core) + Minimal Versioning
Production-Grade Engineering Brief — for Claude Code

0. Goal
Prevent corruption of focused_focus_sessions by implementing timestamp-based conflict detection. Ensure Google Calendar is the source of truth while protecting against:

Out-of-order webhook delivery
Stale Google API responses overwriting fresher local state
Deletions vs updates applied in wrong order

Not optimizing for: Multi-worker coordination, burst traffic, distributed systems (single-instance MVP).

1. Core Decision Logic
1.1 Existing Schema (from 6A)
pythonclass FocusedFocusSession:
    google_updated_at: datetime  # From Google event.updated
    updated_at: datetime          # Local DB last change (auto)
    version: int                  # Counter, currently unused
1.2 Conflict Resolution Rules
For each incoming Google event (from sync or webhook-triggered sync):
python# Load local row by (user_id, google_event_id, google_calendar_id)

if local_row is None:
    # New event
    INSERT with version=1, google_updated_at=event.updated
    
elif google_updated_at > local.google_updated_at:
    # Google is newer → accept update
    UPDATE all fields
    version = local.version + 1
    google_updated_at = event.updated
    
elif google_updated_at < local.google_updated_at:
    # Google is stale → skip
    LOG "Skipping stale update for event {id}"
    
else:  # Timestamps equal
    # Fall back to hash comparison (existing 6B logic)
    if sha256_content_hash != local.sha256_content_hash:
        UPDATE all fields
        version = local.version + 1
1.3 Deletion Handling
pythonif google_event.status == 'cancelled' or event_missing_in_sync:
    if google_updated_at >= local.google_updated_at:
        # Safe to delete
        status = 'deleted'
        deleted_at = now()
        version = local.version + 1
    else:
        # Stale deletion signal → skip
        LOG "Ignoring stale deletion for event {id}"

2. Implementation Requirements
2.1 Modify: backend/apps/focused/logic_sync.py
In process_single_event():

Load local event
Apply conflict detection logic (section 1.2)
Call upsert_focus_session() only if update accepted
Add logging for skipped updates

In detect_deleted_events():

Check Google updated_at before soft-deleting
Only delete if Google timestamp ≥ local timestamp
Increment version on deletion

2.2 Modify: backend/apps/focused/models.py
Ensure version field has default:
pythonversion: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
2.3 New: backend/apps/focused/logic_conflicts.py
Create helper function:
pythondef should_accept_update(
    local_event: FocusedFocusSession | None,
    google_updated_at: datetime,
    google_hash: str
) -> tuple[bool, str]:
    """
    Returns (should_update, reason)
    
    Reason values:
    - "new_event"
    - "google_newer" 
    - "hash_changed"
    - "stale_google"
    - "no_change"
    """
    if local_event is None:
        return (True, "new_event")
    
    if google_updated_at > local_event.google_updated_at:
        return (True, "google_newer")
    
    if google_updated_at < local_event.google_updated_at:
        return (False, "stale_google")
    
    # Timestamps equal → check hash
    if google_hash != local_event.sha256_content_hash:
        return (True, "hash_changed")
    
    return (False, "no_change")

3. Integration with 6B and 6C
3.1 With 6B (Event Ingestion)
6D wraps 6B's upsert logic:

6B provided basic sync + hash calculation
6D adds "should I apply this update?" decision layer
Same upsert_focus_session() function, now called conditionally

3.2 With 6C (Description Cleanup)
When local.event_description is NULL (cleaned after 72h):

Conflict detection still compares timestamps first (description-independent)
Hash recompute (6C special case) happens inside "accept update" path
Version increments correctly
New description gets fresh 72h TTL via updated_at


4. Logging
Add structured logs:
pythonlogger.info(
    "Sync conflict: skipping stale Google data",
    extra={
        "user_id": user_id,
        "google_event_id": google_event_id,
        "google_updated_at": google_updated_at.isoformat(),
        "local_updated_at": local.google_updated_at.isoformat(),
        "local_version": local.version
    }
)

logger.info(
    "Sync update: accepting newer Google data",
    extra={
        "user_id": user_id,
        "google_event_id": google_event_id,
        "reason": reason,  # "google_newer" | "hash_changed"
        "new_version": local.version + 1
    }
)

5. Tests
File: tests/focused/test_increment_6d_conflicts.py
5.1 Test Classes
ConflictDetectionTests:

New event → version=1
Google newer → update accepted, version+=1
Google stale → update skipped, version unchanged
Timestamps equal, hash changed → update accepted, version+=1
Timestamps equal, hash same → no update, version unchanged

DeletionTests:
6. Google deletion newer → soft delete, version+=1
7. Google deletion stale → skip, version unchanged
8. Cancelled event with newer timestamp → delete
9. Cancelled event with older timestamp → skip
Out-of-Order WebhookTests:
10. Webhook A (v102) arrives
11. Webhook B (v101) arrives delayed
12. Verify: B is rejected (stale timestamp)
13. Verify: version stays at 102 state
Description Cleanup Integration:
14. Event synced with description
15. Description cleaned (NULL) after 72h
16. Google changes description
17. Verify: update accepted (timestamp check)
18. Verify: new description persists
19. Verify: version increments

6. Acceptance Criteria
Increment 6D is complete when:
Conflict Detection:

✅ Timestamp comparison works (newer/stale/equal)
✅ Version increments on accepted updates
✅ Stale updates logged and skipped
✅ Hash fallback works for equal timestamps

Deletions:

✅ Only delete if Google timestamp ≥ local
✅ Soft delete updates version
✅ Stale deletions skipped

Integration:

✅ Works with 6B sync logic
✅ Works with 6C description cleanup
✅ No regression in existing tests

Tests:

✅ All 19 test cases pass
✅ Coverage ≥95% for conflict logic


7. Out of Scope (Deferred)

Multi-worker coordination
Distributed locking (Redis)
Mass-change burst optimization
Event history table
Version rollback functionality
Cross-calendar conflict detection

These are post-MVP scale concerns.

8. Version Field Usage
Minimal, not over-engineered:

On insert: version = 1
On accepted update: version += 1
Never decrement, never reuse
No extra tables
Purpose: monotonic counter for debugging + future tie-breaking

Not building: Full event history, version diffs, rollback system.Retry

9. Critical Implementation Instructions for Claude Code

9.1 ALWAYS use Google’s updated timestamp as the primary conflict detector

Claude must not compare hashes first.
Claude must not compare local timestamps first.
Claude must not compare local fields first.

Rule:

If google_updated_at ≤ local.updated_at:
    → Skip update (no change OR out-of-order webhook)
Else:
    → Accept update (Google is fresher)


Reason: Google Calendar is the single source of truth.
This solves:

out-of-order webhooks

webhook bursts

stale DB vs fresh Google events

description being NULL locally (post-cleanup)

9.2 Only increment version AFTER a real update

Claude must not increment version:

on no-op updates

on skipped events

on out-of-order webhook events

on non-successful sync

when google_updated_at ≤ local.updated_at

when description cleanup happened

Rule:

if we persist any field changes:
    version = version + 1


Reason:
Version should reflect actual logical changes to the event, not every sync attempt.

If Claude increments version incorrectly, versioning becomes meaningless and conflict detection collapses.

9.3 MUST integrate the 6C “NULL-description special case” into 6D conflict detection

Claude Code will otherwise forget this and break your entire description-retention system.

Claude must add this:

If local.event_description is None:
    Recompute hash using Google event (description included)
    If hash != local.sha256_content_hash:
        Accept update
    else:
        Skip update
    (continue to next event, do NOT run normal sync logic)


Reason:
After the 72h cleanup job, local descriptions disappear.
If Claude does not re-hash from Google’s full data, the sync will:

❌ miss real updates
❌ incorrectly skip changed events
❌ break version ordering
❌ cause hash drift
❌ produce inconsistent data
