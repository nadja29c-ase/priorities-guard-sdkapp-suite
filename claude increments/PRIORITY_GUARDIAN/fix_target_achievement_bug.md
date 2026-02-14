# Fix: Target Achievement Percentage Bug

## Problem

When a user changes their `weekly_hour_target`, the cumulative percentage on FlexibleCard becomes wrong.

**Current (buggy) flow:**
1. `snapshot_service._update_aggregates` stores `AVG(actual_hours)` → `pg_priorities.avg_hours_week`
2. Widget computes: `avg_hours_week / current_weeklyHourTarget * 100`
3. If target changes from 10h→5h, old hours are divided by new target → wildly wrong percentage

**Example:** User had target=10h for 3 weeks (hit 8h, 9h, 8h), changes to 5h.
- Buggy: `AVG(8,9,8) = 8.3 / 5 * 100 = 166%`
- Correct: per-week `80%, 90%, 80%` → `AVG = 83%`

## Fix

Compute achievement percentage per-snapshot using that snapshot's `target_hours`, aggregate server-side, store as `avg_target_achievement` on `pg_priorities`. Widget reads it directly — no frontend division.

### Design Decisions

- **Arithmetic average (unweighted)**: each week counts equally — answers "How consistent am I week-to-week?" not "What's my total volume ratio?"
- **Include zero-hours weeks**: Zero weeks contribute 0% to the average. If you commit 5h/week and don't show up, the number drops. That's accountability. Streak tracks current momentum (streak=0 means stopped); achievement tracks cumulative commitment fulfillment. No overlap.
- **No cap at 100%**: >100% is real data. A freelancer consistently at 160% on one priority may be neglecting others. Dashboard shows facts.
- **Minimum 2 weeks with snapshots**: below 2 data points, `avg_target_achievement` stays NULL. Widget shows placeholder "Building your average…" instead. Two weeks = a pace.
- **Backend is single source of truth**: widget never computes percentages from raw hours.

---

## Changes By Layer

### 1. Schema — `db_models.py`

Add to `PgPriority` class, after `total_hours_invested`:

```
avg_target_achievement  Numeric(6, 2), nullable=True
```

Comment: `"Average % of weekly target achieved across all snapshotted weeks. NULL when < 2 data points."`

### 2. Migration

New Alembic migration. Single `ADD COLUMN avg_target_achievement NUMERIC(6,2) NULL` on `pg_priorities`. No backfill needed — next dashboard load triggers snapshot pipeline which will populate it.

Downgrade: `DROP COLUMN avg_target_achievement`.

### 3. Snapshot Service — `snapshot_service.py`

In `_update_aggregates`, add computation **after** existing `avg_hours` and `total_hours` queries:

**SQL logic:**
```sql
SELECT AVG(actual_hours * 100.0 / NULLIF(target_hours, 0)), COUNT(*)
FROM pg_weekly_snapshots
WHERE priority_id = :priority_id
  AND target_hours IS NOT NULL
  AND target_hours > 0
```

**Storage logic:**
- If `count >= 2`: store the AVG result as `avg_target_achievement`
- If `count < 2`: store NULL

Add `avg_target_achievement` to the UPDATE statement alongside existing aggregates.

**Important:** `avg_hours_week` and `total_hours_invested` computation stays unchanged — retained for potential weekly report use.

**CRITICAL — zero-hour snapshots already work correctly.** The existing snapshot pipeline (`_create_snapshots_for_week`) creates snapshot rows unconditionally — there is no `if actual_hours > 0` guard. Weeks with 0 matched hours produce rows with `actual_hours=0`. This means zero-hours weeks already contribute 0% to the average via the SQL above. Do NOT add any skip condition for zero-hour weeks.

### 4. Priorities Router — `priorities_router.py`

In `build_priorities_response`, add to `priority_data` dict alongside existing aggregates:

```python
priority_data["avg_target_achievement"] = float(p.avg_target_achievement) if p.avg_target_achievement is not None else None
```

### 5. MCP Layer — `get_priorities.py`

In `_normalize_priority`, add to result dict:

```python
"avgTargetAchievement": p.get("avg_target_achievement"),
```

### 6. Widget Types — `types.ts`

Add to `Priority` interface:

```typescript
avgTargetAchievement?: number | null  // Cumulative % of weekly target. NULL when < 2 snapshotted weeks.
```

### 7. FlexibleCard — `FlexibleCard.tsx`

Replace the percentage computation block. Current code computes `Math.round((avgHoursWeek / weeklyHourTarget) * 100)`.

New logic:
- `avgTargetAchievement != null` → show `~{Math.round(avgTargetAchievement)}% of weekly target on avg` in `text-xs text-secondary`
- `avgTargetAchievement == null AND weeklyHourTarget > 0` → show `Building your average…` in `text-xs text-tertiary`

Do NOT include the numeric target in the display string. The average was computed against historical targets which may differ from the current one. The percentage IS the signal. The user already sees their current target on the card.

Remove the existing `avgHoursWeek != null` vs `null` branching for percentage display. The "First week — tracking" message is replaced by "Building your average…" which covers both first-week and second-week cases (threshold is 2 snapshotted weeks).

`totalHoursInvested` display line stays unchanged.

### 8. Widget Tests — `App.test.tsx`

**Replace/update these FlexibleCard tests:**

| # | Test | Assertion |
|---|---|---|
| 1 | `avgTargetAchievement` renders when present | `avgTargetAchievement: 84.0` → `"~84% of weekly target on avg"` |
| 2 | Shows placeholder when `avgTargetAchievement` is null | `avgTargetAchievement: null, weeklyHourTarget: 5` → `"Building your average"` |
| 3 | Hides percentage when `weeklyHourTarget` is null/0 | No percentage section, no placeholder |
| 4 | Rounding: `avgTargetAchievement: 49.8` → `"~50%"` | Math.round boundary |
| 5 | Allows > 100%: `avgTargetAchievement: 160.5` → `"~161%"` | No cap |
| 6 | Stats hidden in edit mode | `avgTargetAchievement` and `totalHoursInvested` both hidden |

**Remove these tests (no longer applicable):**
- "calculates percentage correctly: 4.2/5 = 84%" (widget no longer computes)
- "First week — tracking" test (replaced by placeholder)
- "rounds percentage correctly at boundary: 2.49/5 = 50%" (widget no longer computes)

---

## What NOT To Change

- `avg_hours_week` column and its computation — currently unused on dashboard, retained for weekly report
- `total_hours_invested` column and its computation
- `compute_flex_status` / `compute_pacing_status` in weekly_report_service
- PgWeeklySnapshot schema (already has `target_hours`)
- DeadlineCard (no aggregate stats)
- Snapshot creation logic in `_create_snapshots_for_week` — already creates rows for zero-hour weeks

---

## Unit Tests (snapshot_service)

| # | Scenario | Expected |
|---|---|---|
| 1 | 3 snapshots: actual=[8,9,7], target=[10,10,10] | `avg_target_achievement = AVG(80,90,70) = 80.0` |
| 2 | Target changes: actual=[8,4], target=[10,5] | `AVG(80,80) = 80.0` (not 120% from raw hours / new target) |
| 3 | One zero week: actual=[8,0,9], target=[10,10,10] | `AVG(80,0,90) = 56.7` (zero week contributes 0%) |
| 4 | Only 1 week with snapshot | `avg_target_achievement = NULL` (below threshold) |
| 5 | No snapshots | `avg_target_achievement = NULL` |
| 6 | All zero-hours weeks: actual=[0,0], target=[10,10] | `AVG(0,0) = 0.0` (not NULL — 2 weeks exist) |
| 7 | >100%: actual=[12], but only 1 week | `NULL` (below 2-week threshold) |
| 8 | >100%: actual=[12,15], target=[10,10] | `AVG(120,150) = 135.0` (no cap) |

## Integration Tests (separate from unit tests)

| # | Scenario | Validates |
|---|---|---|
| 1 | Create 2 snapshots for flexible priority, verify `avg_target_achievement` populated on `pg_priorities` | Full pipeline: snapshot → aggregate update → DB column |
| 2 | Create 1 snapshot only, verify `avg_target_achievement` is NULL | Threshold enforcement |
| 3 | Verify router response includes `avg_target_achievement` field | API contract |

---

## Files To Modify

1. `backend/apps/priority_guardian/db_models.py` — add column
2. `backend/alembic/versions/` — new migration
3. `backend/apps/priority_guardian/services/snapshot_service.py` — add computation in `_update_aggregates`
4. `backend/apps/priority_guardian/routers/priorities_router.py` — include in response
5. `mcp_server/priority_guardian/tools/get_priorities.py` — map to camelCase
6. `mcp_server/priority_guardian/widget-react/src/types.ts` — add field
7. `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx` — use new field
8. `mcp_server/priority_guardian/widget-react/src/__tests__/App.test.tsx` — update tests
9. Rebuild widget: `cd mcp_server/priority_guardian/widget-react && npm run build`
