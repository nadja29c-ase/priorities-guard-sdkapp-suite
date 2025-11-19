# Increment #6B: Event Ingestion Pipeline

**Goal:** Sync Google Calendar events into `focused_focus_sessions` when `needs_sync` flag is set.

---

## Critical Corrections Applied

**CRITICAL fixes:**
1. ✅ `timeMin = now() - 1 day` (catches delayed webhooks, past event updates)
2. ✅ Check `google_updated_at` separately (detects non-content changes)
3. ✅ Explicit all-day detection: `if "dateTime" not in event["start"]: skip`
4. ✅ Transaction boundaries: `async with session.begin():`

**Production safeguards:**
5. ✅ Reuse Increment 4 keyword matching (no conflicting normalization)
6. ✅ Sync ONLY when `needs_sync` exists (no periodic sync)
7. ✅ Skip events with missing `updated` field or unparseable timestamps
8. ✅ Use `datetime.now(timezone.utc)` everywhere
9. ✅ Full resync (no syncToken, no updatedMin)
10. ✅ Delete `needs_sync` ONLY on success

**Final refinements:**
11. ✅ `event_summary` unlimited TEXT (no truncation)
12. ✅ `last_synced_at` batch update AFTER all operations (not per-row)
13. ✅ `timeMax = now() + 30 days` (not 90 - reasonable future window)
14. ✅ Soft-delete cleanup deferred to future increment

---

## Scope

### 1. Sync Trigger
- Check Redis key `focused:needs_sync:{user_id}` (set by Increment 5)
- If exists → fetch events from Google Calendar API
- If not exists → skip (no sync needed)

### 2. Event Fetching
- Call Google Calendar API: `events.list`
- Parameters:
  - `calendarId = "primary"`
  - `singleEvents = true` (flatten recurring events)
  - `timeMin = now() - 1 day` (includes recent past for delayed webhooks, past event updates)
  - `timeMax = now() + 30 days` (reasonable future window for upcoming focus blocks)
  - `maxResults = 250` per page
  - `orderBy = "startTime"`
- Handle pagination via `nextPageToken`
- Auto-refresh Google tokens if expired (reuse Increment 3)
- **No syncToken, no updatedMin** - always full resync

### 3. Event Processing (Per Event)
For each event returned:

**A. Validate Event Type:**
```python
# Skip all-day events (no time component)
if "dateTime" not in event["start"] or "dateTime" not in event["end"]:
    skip_event  # all-day event

# Skip events with missing updated field
if "updated" not in event:
    skip_event  # missing timestamp metadata
    
# Skip events with unparseable timestamps
try:
    start_time = parse_datetime(event["start"]["dateTime"])
    end_time = parse_datetime(event["end"]["dateTime"])
    google_updated_at = parse_datetime(event["updated"])
except (ValueError, KeyError):
    skip_event  # malformed timestamp
```

**B. Extract Fields:**
**B. Extract Fields:**
- `google_event_id` = event.id
- `google_ical_uid` = event.iCalUID
- `google_updated_at` = event.updated (ISO 8601 → UTC)
- `event_summary` = event.summary (nullable)
- `event_description` = event.description (nullable, max 8192 chars)
- `start_time` = event.start.dateTime (convert to UTC)
- `end_time` = event.end.dateTime (convert to UTC)

**C. Calculate SHA256 Hash:**
```python
sha256_content_hash = SHA256({
    "id": google_event_id,
    "summary": event_summary or "",
    "description": event_description or "",
    "start": start_time.isoformat(),
    "end": end_time.isoformat()
})
```

**D. Keyword Matching (Focus Block Detection):**
- Fetch user's keywords from `focused_user_keywords` table (+ system defaults: "focus", "deep work")
- **Reuse existing matching logic from Increment 4** (check_calendar tool)
- Call `matches_focus_keywords(event_summary, keywords)` from existing codebase
- Do NOT create new normalization logic - use identical matching to check_calendar
- If match found:
  - `is_focus_block = TRUE`
  - `matched_keyword = <keyword>`
- If no match or summary is NULL:
  - `is_focus_block = FALSE`
  - `matched_keyword = NULL`

**E. Upsert Logic:**
```sql
-- Query existing event
SELECT id, sha256_content_hash, google_updated_at, status 
FROM focused_focus_sessions 
WHERE user_id = :user_id 
  AND google_event_id = :google_event_id 
  AND google_calendar_id = 'primary'
```

**If event exists:**
- Compare `google_updated_at` first (timestamp from Google)
- If `google_updated_at` > stored timestamp → UPDATE (event modified in Google)
- Else compare hashes:
  - If hash different → UPDATE (content changed)
  - If hash same → SKIP (no changes)
- If status = 'deleted' → UPDATE + set status = 'active' (event restored)

**If event doesn't exist:**
- INSERT new row

**Critical:** google_updated_at check catches non-content changes (reminders, color) that don't affect hash

### 4. Deleted Event Detection
- After processing all API events, identify "orphaned" DB events
- Query:
```sql
SELECT google_event_id 
FROM focused_focus_sessions 
WHERE user_id = :user_id 
  AND google_calendar_id = 'primary'
  AND status = 'active'
  AND google_event_id NOT IN (:fetched_event_ids)
```
- For each orphaned event:
  - SET `status = 'deleted'`
  - SET `deleted_at = NOW()`
  - Do NOT delete from DB (soft delete for conflict detection)

### 5. Sync Sequence & Flag Management

**Execution Order:**
1. Read `needs_sync` flag from Redis
2. If flag exists → perform full sync:
   - Fetch all pages from Google API
   - Process and upsert all events
   - Detect and soft-delete orphaned events
   - **Batch update `last_synced_at` for all active events**
3. If sync succeeds → DELETE Redis key `focused:needs_sync:{user_id}`
4. If sync fails → DO NOT delete flag (allows retry)

**Critical:** 
- Do NOT sync unless `needs_sync` flag exists
- Do NOT add periodic/scheduled sync
- Only webhook events trigger sync (via flag)
- Flag deletion ONLY on complete success
- `last_synced_at` updated ONCE at end, not per event

---

## Files to Create/Modify

1. **backend/apps/focused/logic_sync.py** (NEW)
   - `sync_calendar_events(user_id)` - main sync function
   - `fetch_google_events(user_id, time_min, time_max)` - API fetch + pagination
   - `process_event_batch(user_id, events)` - batch upsert
   - `detect_deleted_events(user_id, fetched_ids)` - soft delete orphans
   - `update_last_synced_timestamp(user_id)` - batch update after all operations
   - `matches_focus_keywords(summary, keywords)` - reuse from Increment 4

2. **backend/core/google_calendar.py**
   - Add `list_events()` method to existing GoogleCalendarClient
   - Handle pagination
   - Parse event fields

3. **backend/apps/focused/focused_router.py**
   - Add endpoint: `POST /api/focused/sync_calendar` (manual trigger for testing)

4. **tests/focused/test_increment_6b.py** (NEW)
   - Test sync logic

---

## Production-Ready Requirements

### Error Handling
- **Token expired:** Auto-refresh (Increment 3 integration)
- **API quota exceeded (429):** Exponential backoff, return error
- **Network failures:** Retry 3x with backoff, then fail gracefully
- **Invalid event data:** Log warning, skip event, continue processing
- **Partial page failure:** Process successful pages, log failure
- **DB transaction failure:** Rollback, retry once, then fail

### Rate Limiting
- Respect Google API limits:
  - ~300 requests/minute/user
  - ~600 requests/minute/project
- Batch upserts (max 100 events per transaction)
- Add 100ms delay between paginated requests if >3 pages

### Transaction Management
- Wrap upsert batch in DB transaction using explicit async transaction:
```python
async with session.begin():
    # batch upsert operations here
    # commit automatic on exit if no exception
```
- Commit after each batch (don't wait for all pages)
- If transaction fails → rollback automatic, log error, continue with next batch
- Max 100 events per transaction
- **Critical:** Do NOT call `session.commit()` inside loop

### Datetime Handling
- **All datetime.now() calls MUST use:** `datetime.now(timezone.utc)`
- Never use naive datetime objects
- Google API returns RFC3339 → parse with timezone awareness
- Convert all to UTC before storing
- Store in `start_time`, `end_time` as TIMESTAMPTZ

### Pagination
- Use `nextPageToken` from API response
- Maximum 10 pages per sync (2500 events)
- If more pages exist → log warning, stop (edge case protection)

### Full Resync Strategy
- **Always perform full 90-day resync**
- Do NOT use `syncToken` from Google API
- Do NOT use `updatedMin` parameter
- Do NOT query only changed events
- This is intentional - incremental sync deferred to future optimization
- Full resync ensures data consistency and simplifies conflict detection

### Data Validation
- `event_summary` is TEXT (unlimited) - do NOT truncate (schema allows unlimited length)
- `event_description` truncate to 8192 chars (Google Calendar limit)
- **Skip all-day events:** Check `if "dateTime" not in event["start"]`
- **Skip events missing updated field:** Check `if "updated" not in event`
- **Skip unparseable timestamps:** Wrap datetime parsing in try/except, skip on failure
- Skip events with missing start/end times
- Validate `start_time < end_time`

---

## Testing Scenarios

1. **Empty calendar:** Fetch returns 0 events → no DB changes
2. **New events:** 5 new events → 5 inserts
3. **Updated events (hash change):** 2 existing events with new hash → 2 updates
4. **Updated events (timestamp only):** 1 event with newer google_updated_at but same hash → 1 update
5. **Unchanged events:** 3 existing events, same hash and timestamp → 3 skips
6. **Deleted events:** 2 DB events not in API response → 2 soft deletes
7. **Restored events:** 1 deleted event reappears in API → status = 'active'
8. **Focus block detection:** Event with "Deep-Work" in title → matches using Increment 4 logic
9. **Empty summary:** Event with NULL summary → is_focus_block = FALSE
10. **All-day event:** Event with only "date" field → skipped
11. **Missing updated field:** Event without "updated" field → skipped
12. **Malformed timestamp:** Event with invalid dateTime → skipped
13. **Pagination:** 300 events → processes 2 pages correctly
14. **Token refresh:** Expired token triggers auto-refresh before API call
15. **API rate limit:** 429 response triggers backoff
16. **Transaction rollback:** DB error mid-batch rolls back batch only
17. **Sync flag persistence:** Sync fails → needs_sync NOT deleted
18. **Past event update:** Event from yesterday updated → synced via timeMin=-1day
19. **last_synced_at batch update:** After successful sync → all active events have identical last_synced_at timestamp

---

## Database Operations

**Batch Upsert (PostgreSQL):**
```sql
INSERT INTO focused_focus_sessions (
    user_id, google_event_id, google_calendar_id,
    google_ical_uid, google_updated_at,
    event_summary, event_description,
    start_time, end_time,
    is_focus_block, matched_keyword,
    sha256_content_hash, status,
    created_at, updated_at
) VALUES (...) 
ON CONFLICT (user_id, google_event_id, google_calendar_id)
DO UPDATE SET
    google_updated_at = EXCLUDED.google_updated_at,
    event_summary = EXCLUDED.event_summary,
    event_description = EXCLUDED.event_description,
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    is_focus_block = EXCLUDED.is_focus_block,
    matched_keyword = EXCLUDED.matched_keyword,
    sha256_content_hash = EXCLUDED.sha256_content_hash,
    status = 'active',
    updated_at = NOW()
WHERE focused_focus_sessions.google_updated_at < EXCLUDED.google_updated_at
   OR focused_focus_sessions.sha256_content_hash != EXCLUDED.sha256_content_hash
   OR focused_focus_sessions.status = 'deleted';
```

**Critical:** 
- Update triggers on either timestamp change OR hash change OR deleted status
- `last_synced_at` NOT updated here - see batch update below

**Batch Update last_synced_at (after all upserts complete):**
```sql
-- Only after ALL page processing succeeds
UPDATE focused_focus_sessions
SET last_synced_at = NOW()
WHERE user_id = :user_id 
  AND google_calendar_id = 'primary'
  AND status = 'active';
```

**Critical:** `last_synced_at` updated ONCE per sync run, not per row

---

## Integration Points

**From Increment 3:** Token refresh logic  
**From Increment 4:** Google Calendar API client  
**From Increment 5:** `needs_sync` Redis flag  
**From Increment 6A:** `focused_focus_sessions` table schema

---

## Success Criteria

✅ `needs_sync` flag triggers event fetching  
✅ Google API returns events correctly  
✅ Events upserted into DB based on google_updated_at OR hash comparison  
✅ Deleted events soft-deleted in DB  
✅ Focus blocks identified via Increment 4 keyword matching  
✅ `last_synced_at` batch updated ONCE after all operations  
✅ `needs_sync` flag cleared after successful sync  
✅ Pagination handles >250 events  
✅ Token refresh integrated seamlessly  
✅ API rate limits respected  
✅ Transaction failures handled gracefully  
✅ All-day and malformed events skipped  
✅ Events with missing `updated` field skipped  
✅ All test scenarios pass

---

## Known Limitations (Intentional)

- Only "primary" calendar synced
- Sync window: `now() - 1 day` to `now() + 30 days`
- All-day events skipped (no dateTime component)
- Max 2500 events per sync (10 pages)
- No sync status tracking yet (future: focused_sync_history table)
- Full resync only (no incremental syncToken optimization)
- No conflict detection yet (Increment 7)
- Keywords use existing Increment 4 matching logic
- **Soft-delete cleanup NOT implemented** - deleted events older than 90 days remain in DB until cleanup job (future increment)

---

## What's OUT of Scope

❌ Conflict detection (SHA256 comparison for alerts - Increment 7)  
❌ run_focus_mode() automation triggers (Increment 8)  
❌ Focus pattern analytics (later)  
❌ Multi-calendar support (later)  
❌ Sync history/audit table (later)  
❌ Incremental sync with syncToken (optimization for later)  
❌ Real-time webhook processing (that's trigger only - this is the sync)

---

# MANDATORY IMPLEMENTATION RULES (Claude: DO NOT VIOLATE THESE)

Do not infer fields from Google API. Only store fields defined in Increment 6A.
Do not modify the database schema, field names, types, or indexes.
Do not add new indexes or new defaults.
Do not use SQLAlchemy bulk operations.
Do not use onupdate, event listeners, or automation for timestamps.
Do not update last_synced_at inside ON CONFLICT or inside per-row logic. Update ONCE at the end of sync.
Use datetime.fromisoformat(ts.replace("Z", "+00:00")) for parsing. No dateutil.
Keyword matching must reuse matches_focus_keywords() from Increment 4 — no new normalization logic.
Pagination must stop after 10 pages even if nextPageToken exists.
**UPDATE decisions must follow this exact priority:

google_updated_at newer

hash changed

resurrect deleted

else skip**
Skip invalid events silently; never throw.
Only (user_id, google_event_id, google_calendar_id) identifies events.
All database operations must be inside async with session.begin().
Never physically delete events; only soft-delete.
All datetimes must be timezone-aware UTC.
Never run keyword matching on all-day events.


All-day Event Claude Code Behavior:

Definitions of all-day events:
if "dateTime" not in event["start"] or "dateTime" not in event["end"]:
    # all-day event → skip


- Do NOT ingest all-day events.
- Do NOT treat them as Focus Blocks even if they contain focus keywords.
- Do NOT convert date fields to timestamps.
- Do NOT store them in the database.
- Do NOT run hashing or keyword detection on them.
- They do NOT trigger Focus Mode.