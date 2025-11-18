# Increment #6A: Event Data Model + Migration

**Goal:** Define and create `focused_focus_sessions` table for calendar event storage.

---

## Key Corrections from Initial Version

**Critical fixes:**
1. ✅ `event_summary` now NULL (Google allows empty titles)
2. ✅ SHA256 includes description (detects description-only updates)
3. ✅ `google_ical_uid` NOT NULL (always present, stable identifier)
4. ✅ `status` ENUM type (enforces valid states at DB level)
5. ✅ Removed `is_recurring` (unnecessary - icalUID groups instances)

**Final refinements:**
6. ✅ SHA256 index composite with `user_id` (prevents cross-user scans)
7. ✅ Added `google_updated_at` (Google's timestamp for conflict detection ordering)
8. ✅ `event_description` max 8192 chars (matches Google Calendar limit)

**Bonus improvements:**
- Added `last_synced_at` for diagnostics
- Added `version` for future history tracking
- Added index on `google_ical_uid` for recurrence queries

---

## Table Schema: `focused_focus_sessions`

**Purpose:** Store calendar events from Google Calendar, identify focus blocks, enable conflict detection.

**Lifecycle:** 90-day rolling retention (GDPR compliance)

### Columns

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | Internal identifier |
| `user_id` | UUID | FK → core_users, NOT NULL, INDEX | Owner |
| `google_event_id` | VARCHAR(255) | NOT NULL | Google's event.id |
| `google_calendar_id` | VARCHAR(255) | NOT NULL, DEFAULT 'primary' | Calendar source |
| `event_summary` | TEXT | NULL | Event title (keyword matching, can be empty) |
| `event_description` | TEXT | NULL | Event body text (max 8192 chars) |
| `google_updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | Google's last modified timestamp |
| `start_time` | TIMESTAMP WITH TIME ZONE | NOT NULL, INDEX | UTC start time |
| `end_time` | TIMESTAMP WITH TIME ZONE | NOT NULL, INDEX | UTC end time |
| `is_focus_block` | BOOLEAN | NOT NULL, DEFAULT FALSE, INDEX | Matched focus keyword |
| `matched_keyword` | VARCHAR(100) | NULL | Which keyword triggered match |
| `sha256_content_hash` | CHAR(64) | NOT NULL, INDEX | Deduplication + change detection |
| `status` | ENUM('active', 'deleted') | NOT NULL, DEFAULT 'active' | Event lifecycle state |
| `google_ical_uid` | VARCHAR(255) | NOT NULL, INDEX | iCalendar UID (stable across updates) |
| `last_synced_at` | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT NOW() | Last sync from Google |
| `version` | INTEGER | NOT NULL, DEFAULT 1 | Event version (for history tracking) |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT NOW() | First sync |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT NOW() | Last modified |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | NULL | Soft delete timestamp |

---

## Indexes

```sql
CREATE UNIQUE INDEX idx_focus_sessions_user_event 
  ON focused_focus_sessions(user_id, google_event_id, google_calendar_id);

CREATE INDEX idx_focus_sessions_start_time 
  ON focused_focus_sessions(start_time);

CREATE INDEX idx_focus_sessions_end_time 
  ON focused_focus_sessions(end_time);

CREATE INDEX idx_focus_sessions_focus_blocks 
  ON focused_focus_sessions(user_id, is_focus_block) 
  WHERE status = 'active';

CREATE INDEX idx_focus_sessions_user_hash 
  ON focused_focus_sessions(user_id, sha256_content_hash);

CREATE INDEX idx_focus_sessions_cleanup 
  ON focused_focus_sessions(created_at) 
  WHERE status = 'active';

CREATE INDEX idx_focus_sessions_ical_uid 
  ON focused_focus_sessions(google_ical_uid);
```

---

## Design Decisions

### SHA256 Hash Calculation
```python
sha256_content_hash = SHA256({
    "id": google_event_id,
    "summary": event_summary or "",
    "description": event_description or "",
    "start": start_time.isoformat(),
    "end": end_time.isoformat()
})
```
**Purpose:** Detect content changes (summary, description, timing) for conflict detection (Increment 7)  
**Critical:** Description MUST be included to detect description-only updates

### Google Update Timestamp
- Store `google_updated_at` from Google event.updated field
- Essential for conflict detection ordering (prevents update thrashing)
- Helps detect API-level race conditions
- Sorted by this field when processing batch updates

### Hash Index Strategy
- Composite index `(user_id, sha256_content_hash)` prevents cross-user scan
- Scopes queries per user for better performance
- Prevents inefficiency from rare hash collisions between users

### Timezone Strategy
- **Store:** All timestamps in UTC
- **Display:** Convert to user timezone in application layer
- **Rationale:** Simplifies queries, prevents DST issues

### Recurring Events
- Fetch with `singleEvents=true` (Google API flattens all instances)
- Each occurrence stored as separate row
- Link via `google_ical_uid` (all instances share same UID)
- Individual occurrences can be modified/deleted independently
- No `is_recurring` flag needed - infer from icalUID grouping in analytics

### Status Enum
- PostgreSQL ENUM type: `('active', 'deleted')`
- Enforces valid states at database level
- Prevents invalid values ("Deleted", "DELETED", "inactive", etc.)

### Soft Delete
- Set `status = 'deleted'` and `deleted_at = NOW()`
- Preserve for conflict detection window
- Hard delete via cleanup job after 90 days

### Focus Block Detection
- `is_focus_block = TRUE` when `event_summary` matches keyword
- Handle NULL/empty summaries: `is_focus_block = FALSE`
- Store `matched_keyword` for analytics
- Reuse check_calendar matching logic (case-insensitive, title-only)

### Empty Event Titles
- `event_summary` can be NULL (Google Calendar allows empty titles)
- Application layer defaults to empty string for display
- Keyword matching skips NULL/empty summaries

---

## GDPR Compliance

**Retention:** 90 days from `created_at`  
**Cleanup:** Daily Celery job (future increment)  
**Data Minimization:**
- No attendee data
- No location data
- No extended properties
- Only title + timestamps + Google metadata (updated_at, ical_uid)
- Description stored for conflict detection only

---

## Migration File

**File:** `backend/alembic/versions/YYYYMMDD_HHMM_add_focused_focus_sessions.py`

**Actions:**
1. Create ENUM type `event_status_enum AS ENUM ('active', 'deleted')`
2. Create table with all columns
3. Create all indexes
4. Add foreign key constraint to core_users
5. Add check constraint: `start_time < end_time`
6. Add check constraint: `version >= 1`

---

## Validation Rules

**Application Layer (SQLAlchemy model):**
- `google_event_id` max 255 chars, required
- `google_ical_uid` max 255 chars, required
- `google_updated_at` required (from Google event.updated field)
- `event_summary` nullable, max 2000 chars if present
- `event_description` nullable, max 8192 chars if present (Google Calendar limit)
- `start_time` must be < `end_time`
- `sha256_content_hash` exactly 64 hex chars, required
- `status` ENUM validation ('active', 'deleted')
- `matched_keyword` max 100 chars, nullable
- `version` >= 1
- `last_synced_at` auto-updated on modification

---

## Files to Create/Modify

1. **backend/apps/focused/models.py**
   - Add `FocusedFocusSession` SQLAlchemy model
   - Relationships to `CoreUser`
   - Validators

2. **backend/alembic/versions/YYYYMMDD_add_focused_focus_sessions.py**
   - Alembic migration
   - Create table + indexes
   - Rollback support

3. **tests/focused/test_focus_session_model.py**
   - Model validation tests
   - Constraint tests
   - SHA256 hash generation tests

---

## Success Criteria

✅ Migration runs successfully (up + down)  
✅ All indexes created (including composite user_hash index)  
✅ Foreign key constraint enforces user_id  
✅ Unique constraint prevents duplicate events  
✅ Check constraints enforce data integrity  
✅ ENUM type created and enforced  
✅ SQLAlchemy model validates input  
✅ SHA256 hash generation includes description  
✅ google_updated_at properly captured from Google API  
✅ Tests verify schema correctness

---

## Known Limitations (Intentional)

- Recurring events stored as flattened instances (singleEvents=true)
- No attendee tracking
- No location/conferencing data
- Single calendar ("primary") only
- No event color/category
- No reminders storage
- No attachment metadata

**These are deferred by design** - minimal data for MVP.

---

# Critical Implementation Instructions for Claude Code
1. Use EXACT field names and types from the spec

Do NOT infer fields from Google API responses.
Store only the fields defined in the schema above.

2. Use PostgreSQL ENUM for status (not SQLAlchemy string enum)

Create ENUM explicitly in Alembic:

sa.Enum('active', 'deleted', name='event_status_enum')


Do not inline string values.
Do not use SQLAlchemy’s default Python Enum mapping.

3. Use composite index for SHA256 hash

Do NOT create a single-column index.

Correct index:

op.create_index(
    "idx_focus_sessions_user_hash",
    "focused_focus_sessions",
    ["user_id", "sha256_content_hash"]
)

4. google_updated_at MUST come from Google event.updated

This is not optional.

Claude must extract it from the API response.

Example:

google_updated_at = parser.isoparse(event["updated"]).astimezone(timezone.utc)

5. event_description MUST NOT exceed 8192 chars

Truncate if necessary:

desc = event.get("description") or ""
event_description = desc[:8192]

6. SHA256 hash MUST include description and timestamps exactly as spec

Do NOT omit or reformat fields.

7. Use UTC everywhere

Never store naive datetimes.

8. Soft delete only

Never delete rows physically.
Set:

status = 'deleted'
deleted_at = now()

9. The model and migration MUST match exactly

Claude tends to drift; enforce:

same field order

same naming

same defaults

same enums

same column types

10. Add Alembic downgrade()

Claude often forgets rollback logic.
Require full symmetry.

11. SQLAlchemy model MUST enforce validation rules

If values exceed length, raise ValueError.

12. google_ical_uid MUST be NOT NULL

Claude sometimes sets it nullable — disallow this.

13. No cascade on delete for user_id

Prevent accidental wipes.
Use:

ondelete="RESTRICT"

14. last_synced_at MUST NOT be modified outside Increment 6

Claude tends to auto-update via SQLAlchemy events — forbid that here.

15. Never include user timezone in stored timestamps

Store UTC only.

16. Do NOT add indexes not listed in the spec

Claude often auto-suggests extra indexes — forbid them.

17. The SQLAlchemy model MUST reflect the ENUM type name exactly

Name must match:

event_status_enum

18. google_calendar_id default MUST be 'primary'

Do NOT infer from event body.

19. Require typing.StrictModel for Pydantic validations

Avoid silent coercion.

20. Require explicit imports from backend.apps.focused

Prevent circular imports.

Follow the schema and constraints EXACTLY as written. Do not introduce fields, logic, or defaults not explicitly defined.