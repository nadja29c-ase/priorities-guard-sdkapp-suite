Increment 6C — Description Cleanup, Sync Correctness & Retention Enforcement
(Final, Production-Ready Version)
0. Goal

Implement GDPR-compliant short-term retention of event_description, while maintaining correct sync behavior.

Specifically:

Store event_description only for recent sync correctness + debugging

Automatically delete descriptions after 72 hours

Ensure sync logic still detects changes when local description is already deleted

Maintain the existing SHA256 hash design (includes description)

No schema changes.
Only logic + tests.

1. Context / Requirements
Data Model

event_description is:

stored temporarily (≤72h)

part of the SHA256 change-detection hash

irrelevant for long-term focus pattern analysis

description ∈ hash(id, summary, description, start, end)

Retention Policy

event_description: delete after 72h

all other focus session data: retain ≤ 90 days

Key Compliance Note

If a user edits the event frequently, the description remains.
This is GDPR-compliant, because the data is still in active processing
→ retention window refreshes naturally.

2. Files Added / Modified
New

backend/apps/focused/logic_cleanup.py

tests/focused/test_increment_6c_cleanup.py

Modified

backend/apps/focused/logic_sync.py (NULL-description sync logic)

(Optional) Admin endpoint in router

3. Cleanup Job — Delete Descriptions After 72h
3.1 Configuration

backend/apps/focused/config.py

FOCUSED_DESCRIPTION_TTL = timedelta(hours=72)

3.2 Cleanup Logic (CRITICAL: uses updated_at)

Correct field is updated_at (NOT created_at).

async def cleanup_old_descriptions(session: AsyncSession) -> int:
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - FOCUSED_DESCRIPTION_TTL

    result = await session.execute(
        text("""
            UPDATE focused_focus_sessions
            SET event_description = NULL,
                updated_at = now()
            WHERE status = 'active'
              AND event_description IS NOT NULL
              AND updated_at < :cutoff
        """),
        {"cutoff": cutoff},
    )

    return result.rowcount or 0


Why updated_at?
Because when sync restores a description, it should get a fresh 72h window.

If we used created_at, descriptions would be deleted instantly after sync → broken.

4. Sync Logic Change — Description May Be NULL
Why special logic is needed

After cleanup, the DB has:

description = NULL
hash = old_hash_that_included_original_description


Normal sync logic would either:

treat NULL as a real change (false positive), or

ignore description changes (missed updates)

Therefore:

When local description is NULL → ALWAYS compare hash using Google's full data.

Add this block to sync_calendar():

if local_event and local_event.event_description is None:
    google_start_utc, google_end_utc = normalize_google_times(google_event)

    fresh_hash = calculate_content_hash(
        google_event_id=google_event["id"],
        event_summary=google_event.get("summary"),
        event_description=google_event.get("description"),
        start_time=google_start_utc,
        end_time=google_end_utc,
    )

    if fresh_hash != local_event.sha256_content_hash:
        await upsert_focus_session(
            session=session,
            user_id=user_id,
            google_event=google_event,
            sha256_content_hash=fresh_hash,
        )

    continue  # Skip normal path


This fully solves the cleaned-description edge case.

5. Tests for Increment 6C
5.1 Cleanup Tests

Deletes descriptions older than 72h

Does not delete recent descriptions

CRITICAL: Re-synced descriptions get a fresh 72h window
(validated using updated_at)

5.2 Sync Tests

When local description NULL + Google changed → sync updates description

New description then respects 72h TTL

6. Logging

Add:

logger.info("Focused: cleaned %s event descriptions", rowcount)
logger.info("Focused sync: description NULL but hash changed → updating event")

7. Acceptance Criteria

Increment 6C is considered DONE when:

Cleanup

 Runs and deletes only old descriptions

 Respects updated_at TTL

 Re-synced descriptions do not get deleted prematurely

Sync

 Change detection works with description=NULL

 Hash correctness guaranteed

 No false positives / false negatives

Tests

 All 6C tests pass

