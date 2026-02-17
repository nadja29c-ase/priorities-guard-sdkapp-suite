# Briefing: User-Chosen Keywords & Keyword Reassignment

## Context

Currently `calendar_keyword` (P1/P2/P3) is auto-assigned on creation (first available in order) and immutable afterward. Users expect P1 > P2 > P3 to carry semantic importance. A user who creates their least important priority first gets P1 assigned to it — breaking their mental model.

This feature lets users:
1. **Choose** their keyword on creation
2. **Reassign** keywords at any time — if the chosen keyword is held by another priority, the displaced priority automatically receives the freed keyword

There is no "swap" concept from the user's perspective. They just pick a badge. The cascade is automatic.

**Design Principles:**
- P1/P2/P3 carries semantic meaning (importance ranking chosen by user)
- Keywords are mutually exclusive per user (enforced by existing partial unique index)
- All tracking (snapshots, aggregates, streaks) is keyed by `priority_id` (UUID), NOT keyword — reassignment doesn't break historical data
- Calendar matching is forward-only: after reassignment, future events should use the new keyword. Past snapshots are unaffected.

## Changes Overview

### A. Migration: Make `calendar_keyword` Nullable
### B. Keyword Choice on Creation (Backend + MCP + Widget)
### C. Keyword Reassignment via Update (Backend + MCP + Widget)

---

## A. Migration: Make `calendar_keyword` Nullable

### Why

The keyword reassignment (when the desired keyword is held by another active priority) requires a 3-step swap within a transaction using NULL as a safe intermediary value:

1. Set displaced priority's keyword to NULL
2. Set requesting priority's keyword to desired value
3. Set displaced priority's keyword to freed value

This is necessary because `idx_pg_priorities_user_keyword_active` is a **unique index**, not a deferrable unique constraint. PostgreSQL enforces unique indexes per-row during UPDATE execution, not at statement end. A single `UPDATE ... SET ... CASE` can fail with `duplicate key value violates unique constraint` when two rows temporarily share a keyword value mid-execution.

NULL is safe because:
- CHECK constraint `calendar_keyword IN ('P1', 'P2', 'P3')` passes when value is NULL (CHECK evaluates to UNKNOWN for NULL, which passes)
- Unique indexes allow multiple NULL values
- The NULL value is uncommitted, so other sessions won't observe it under READ COMMITTED isolation (the default). Row locks (`SELECT FOR UPDATE`) prevent concurrent swaps on the same rows.

### Migration file

New Alembic migration: `make_calendar_keyword_nullable.py`

Upgrade:
```sql
ALTER TABLE pg_priorities ALTER COLUMN calendar_keyword DROP NOT NULL;
```

Downgrade:
```sql
-- Fail fast if any NULL rows exist — do not silently mutate semantic data
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_priorities WHERE calendar_keyword IS NULL) THEN
        RAISE EXCEPTION 'Cannot downgrade: NULL calendar_keyword rows exist. Fix data before retrying.';
    END IF;
END$$;

ALTER TABLE pg_priorities ALTER COLUMN calendar_keyword SET NOT NULL;
```

### Model change: `db_models.py`

Update `calendar_keyword` column:
```python
calendar_keyword: Mapped[str | None] = mapped_column(
    String(2),
    nullable=True,  # Changed from False — allows NULL as transient state during keyword reassignment
    comment="Calendar keyword (P1, P2, P3). Nullable only as transient state during keyword reassignment.",
)
```

**Important:** Application logic must NEVER leave `calendar_keyword` as NULL after a transaction completes. NULL is exclusively a transient state during the 3-step swap. Enforce with explicit runtime checks (NOT `assert` — Python `assert` is stripped by `-O` flag).

---

## B. Keyword Choice on Creation

### B1. Backend: `priorities_router.py` — `POST /priorities`

Currently auto-assigns: `assigned_keyword = available_keywords[0]`

Change: Accept optional `calendar_keyword` in the request body.
- If provided AND in `available_keywords` → use it
- If provided but NOT available → return 409 KEYWORD_CONFLICT (widget prevents this via disabled badges, but API must enforce for MCP/ChatGPT path + race conditions)
- If not provided → fall back to auto-assignment (first available, existing behavior)

Note: On creation, there is no cascade/displacement. The keyword must be genuinely available. The widget disables taken keywords in the picker so the user can't select an unavailable one.

**Race condition handling (already in place):** The existing `POST /priorities` code uses `SELECT FOR UPDATE` on the user's active priorities before assigning a keyword. This locks existing rows and prevents concurrent creates from assigning the same keyword. The partial unique index + `IntegrityError` catch is the fallback for the zero-active-priorities race (where SELECT FOR UPDATE locks nothing). This existing pattern covers the new keyword-choice path — no additional concurrency logic needed for creation.

### B2. Backend: `models/requests.py` — `CreatePriorityRequest`

Add optional field:
```python
calendar_keyword: Optional[Literal["P1", "P2", "P3"]] = None
```

No cross-validation needed at model level — the router validates against `available_keywords` at runtime.

### B3. MCP Tool: `create_priority.py`

Add `calendar_keyword` to `INPUT_SCHEMA.properties`:
```json
"calendar_keyword": {
    "type": "string",
    "enum": ["P1", "P2", "P3"],
    "description": "Preferred keyword (optional). If not provided, next available is auto-assigned."
}
```

Update DESCRIPTION: Remove "Do not ask the user to choose a keyword." Replace with: "If the user expresses a preference for which keyword (P1, P2, P3) to assign, include it. Otherwise omit and the backend assigns the next available."

Pass `calendar_keyword` through to backend payload if present in arguments.

### B4. MCP Tool: `widget_tools/add_priority.py`

Add `calendar_keyword` to INPUT_SCHEMA with same spec as B3. Pass through to backend payload if present in arguments.

### B5. Widget: `AddPriorityForm.tsx`

Add a keyword selection step AFTER type selection, BEFORE fields entry. Show all three keywords (P1/P2/P3).

UI: Three tappable badges using existing `BADGE_COLORS` and `BADGE_CIRCLE_CLASS` from `constants.ts`. Available keywords are fully interactive. Unavailable keywords (held by other active priorities) are visually greyed out and disabled (not tappable).

If only 1 keyword available, auto-select it and skip the step.

Include the selected keyword in the `onAdd` callback data. Update the `onAdd` type signature to include `calendar_keyword?: string`.

### B6. Widget: `App.tsx` — `handleAddPriority`

Pass `calendar_keyword` from form data through to the `add_priority` callTool arguments.

---

## C. Keyword Reassignment via Update

### C1. Backend: `priorities_router.py` — `PUT /priorities/{id}`

Currently rejects `calendar_keyword` changes (not in `UpdatePriorityRequest`).

Change: Accept `calendar_keyword` as an updatable field. Three cases:

**Case 0 — Same keyword (no-op):** Requesting priority already has the desired keyword. Return current state, no DB writes.

**Case 1 — Keyword is free:** No other active priority holds the requested keyword. Simple column update on the single row.

**Case 2 — Keyword is held (displacement):** Another active priority owns the desired keyword. Perform atomic 3-step reassignment within the existing transaction.

#### Row Locking (Deadlock Prevention + TOCTOU Safety)

When displacement is needed, follow this sequence to prevent both deadlocks and time-of-check-time-of-use races:

1. **Read** requesting priority (no lock yet)
2. **Determine** desired keyword
3. **Query** displaced priority by keyword (no lock yet)
4. **Build** sorted ID list (smallest UUID first)
5. **Lock** both rows with `SELECT FOR UPDATE` in sorted order
6. **Re-validate** after lock: confirm displaced priority still holds the desired keyword. If not (another transaction reassigned between read and lock), re-evaluate — it may now be free (Case 1) or held by a different priority.
7. **Perform** 3-step swap

```python
# Step 1-3: Initial reads (no locks)
requesting = await fetch_priority(priority_id, user_id, session)
desired_keyword = request.calendar_keyword

displaced = await session.execute(
    select(PgPriority).where(
        PgPriority.user_id == user_id,
        PgPriority.calendar_keyword == desired_keyword,
        PgPriority.status == "active",
    )
)
displaced_priority = displaced.scalar_one_or_none()

if displaced_priority is None:
    # Case 1: keyword is free — simple update
    ...

# Step 4-5: Lock both in deterministic order
ids_to_lock = sorted([requesting.id, displaced_priority.id])
result = await session.execute(
    select(PgPriority)
    .where(PgPriority.id.in_(ids_to_lock))
    .order_by(PgPriority.id)
    .with_for_update()
)
locked = {p.id: p for p in result.scalars().all()}
requesting = locked[requesting.id]
displaced_priority = locked[displaced_priority.id]

# Step 6: Re-validate after lock (TOCTOU defense)
if displaced_priority.calendar_keyword != desired_keyword:
    # State changed between read and lock — re-evaluate
    # May now be free (Case 1) or held by different priority
    ...

# Step 7: Perform 3-step swap
...
```

#### 3-Step Swap

```python
# Both rows locked in deterministic order

# Step 1: Clear displaced priority's keyword (NULL intermediary)
displaced_priority.calendar_keyword = None
await session.flush()

# Step 2: Set requesting priority to desired keyword
requesting_priority.calendar_keyword = desired_keyword
await session.flush()

# Step 3: Set displaced priority to freed keyword
displaced_priority.calendar_keyword = freed_keyword
await session.flush()

# Invariant check (do NOT use assert — stripped by python -O)
if requesting_priority.calendar_keyword is None or displaced_priority.calendar_keyword is None:
    await session.rollback()
    logger.error(
        "priority.reassign.invariant_violation",
        requesting_id=str(requesting_priority.id),
        displaced_id=str(displaced_priority.id),
    )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "INVARIANT_VIOLATION", "message": "Keyword swap left NULL state. This is a bug."},
    )

await session.commit()
```

Each `flush()` sends the UPDATE to PostgreSQL. The unique index is satisfied at each step because NULL doesn't conflict. The NULL value is uncommitted, so other sessions won't observe it (READ COMMITTED isolation). Row locks prevent concurrent swaps on the same rows.

#### IntegrityError Handling

Even with row locks, wrap the swap in a try/except for `IntegrityError`. A third priority could theoretically be modified concurrently (though unlikely with proper locking). Map `IntegrityError` to 409:

```python
except IntegrityError as e:
    await session.rollback()
    logger.warning("priority.reassign.integrity_error", error=str(e))
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "success": False,
            "error": {
                "code": "KEYWORD_CONFLICT",
                "message": "Keyword conflict during reassignment. Please retry.",
            },
        },
    )
```

#### Validation & Error Mapping

| Condition | Response |
|---|---|
| Requesting priority not found / wrong user / not active | 404 NOT_FOUND |
| Desired keyword not in ["P1","P2","P3"] | 422 VALIDATION_ERROR |
| Desired keyword same as current (no-op) | 200 (return current state) |
| Displaced priority not active (shouldn't happen — partial index) | 422 with clear message |
| IntegrityError during swap | 409 KEYWORD_CONFLICT |
| NULL persists after swap | 500 INVARIANT_VIOLATION |

After reassignment, return `build_priorities_response()` (same pattern as all mutation endpoints).

**Important:** Snapshots, aggregates, streaks are all keyed by `priority_id` — they are NOT affected by keyword changes. No recalculation needed.

### C2. Backend: `models/requests.py` — `UpdatePriorityRequest`

Add field:
```python
calendar_keyword: Optional[Literal["P1", "P2", "P3"]] = Field(
    default=None,
    description="Reassign keyword. If held by another active priority, they automatically receive this priority's current keyword.",
)
```

Update `has_updates()` to include `self.calendar_keyword is not None`.

No cross-type validation needed — keyword reassignment is valid for both deadline and flexible priorities.

### C3. MCP Tool: `widget_tools/update_priority.py`

Add `calendar_keyword` to INPUT_SCHEMA:
```json
"calendar_keyword": {
    "type": "string",
    "enum": ["P1", "P2", "P3"],
    "description": "Reassign keyword badge"
}
```

Update tool DESCRIPTION to mention: "If the requested keyword is held by another active priority, they automatically swap keywords."

Pass through to backend payload if present in arguments. No new handler logic — the backend handles the cascade.

### C4. Widget: Priority Cards (edit mode)

In **edit mode** on both FlexibleCard and DeadlineCard, make the keyword badge tappable. Show all three keyword options (P1/P2/P3). The current keyword is visually selected/active. The other two are tappable alternatives.

**Displacement microcopy:** When a keyword is held by another priority, show a brief inline hint on hover/focus: "Will swap with [other priority name]". This keeps the action transparent without adding a confirmation dialog.

Tapping a different keyword calls `update_priority` with `{ priority_id, calendar_keyword: "P1" }`. The backend handles the cascade. The widget re-renders from the fresh priority list returned by structuredContent.

If only 1 active priority exists, all three keywords are shown. Current is selected, other two are tappable (free reassignment, no displacement needed, no microcopy needed).

---

## Unit Tests

### Backend: `tests/unit/priority_guardian/`

**Keyword reassignment tests (new file or extend test_priorities_router.py):**
1. Reassign to free keyword: single row updated, new keyword set
2. Reassign to held keyword (displacement): 3-step swap executes, both keywords correct after
3. Reassign to same keyword (no-op): return current state, no DB writes
4. Reassign on retired priority: return 404
5. Displaced priority gets the freed keyword correctly
6. NULL keyword never persists after transaction commits (invariant check, not assert)
7. Invalid keyword value: return 422
8. IntegrityError during swap: return 409

**Keyword choice on creation tests:**
1. Providing valid available keyword → uses it
2. Providing unavailable keyword → return 409 KEYWORD_CONFLICT
3. Not providing keyword → auto-assigns first available (existing behavior preserved)
4. Providing keyword not in ["P1","P2","P3"] → return 422 validation error

## Integration Tests

### `tests/integration/priority_guardian/test_keyword_reassignment.py`

1. Create two priorities (P1, P2) → reassign P2's priority to P1 → verify: first becomes P1, second becomes P2
2. Create three priorities → reassign P3 to P1 → verify: P3→P1, old P1→P3, P2 untouched
3. Reassign to free keyword (1 priority, currently P1, reassign to P3) → verify simple update
4. Reassign → fetch priorities → verify response has correct updated keywords
5. Reassign → verify snapshots still reference correct `priority_id` (unaffected)
6. Reassign with invalid priority ID → 404
7. Choose keyword on creation → verify assigned correctly
8. Verify no row has NULL calendar_keyword after reassignment transaction
9. Reassign same keyword (no-op) → verify 200 with unchanged data

---

## What Does NOT Change

- `pg_weekly_snapshots` schema: keyed by `priority_id`, not keyword
- `_update_aggregates()`: queries by `priority_id`
- `_compute_streak()`: queries by `priority_id`
- `compute_allocation_from_events()`: reads CURRENT keyword from priority at query time — automatically correct after reassignment
- Weekly report: reads current keyword at query time — automatically correct
- Pie chart: reads keyword from structured data — automatically correct
- No new MCP tool needed
- No new backend endpoint needed
- CHECK constraint `calendar_keyword IN ('P1', 'P2', 'P3')` unchanged — NULL passes CHECK (evaluates to UNKNOWN)
- Partial unique index unchanged — NULL values don't conflict

## Migration

One Alembic migration: `ALTER TABLE pg_priorities ALTER COLUMN calendar_keyword DROP NOT NULL`

Downgrade fails fast if any NULL rows exist (does not silently mutate data).

This is the only schema change. Reversible. No data transformation needed for upgrade.

## Acceptance Criteria

- [ ] Migration applied: `calendar_keyword` is nullable
- [ ] User can choose P1/P2/P3 on creation (widget shows keyword picker)
- [ ] Auto-assignment still works when no keyword is chosen (MCP fallback)
- [ ] Unavailable keywords are greyed out / disabled in creation picker
- [ ] Keyword reassignment via `PUT /priorities/{id}` works for free keywords
- [ ] Keyword reassignment with displacement: displaced priority gets freed keyword automatically via 3-step NULL intermediary
- [ ] Row locking in deterministic order (smallest UUID first) prevents deadlocks
- [ ] IntegrityError caught and mapped to 409
- [ ] NULL keyword never persists outside transaction (explicit runtime check, not assert)
- [ ] Widget edit mode: tappable keyword badges on priority cards
- [ ] Displacement microcopy shown when keyword is held by another priority
- [ ] No-op when user picks the keyword already assigned
- [ ] Historical snapshots unaffected by reassignment
- [ ] All existing tests pass unchanged
- [ ] New unit + integration tests for reassignment and keyword choice
- [ ] Widget rebuilt (`npm run build` in widget-react)
