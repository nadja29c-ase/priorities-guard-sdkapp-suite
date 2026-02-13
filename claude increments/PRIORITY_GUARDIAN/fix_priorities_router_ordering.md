# Fix: priorities_router.py — Ordering bug + falsy conversion bugs

**File:** `backend/apps/priority_guardian/routers/priorities_router.py`
**Function:** `build_priorities_response()`

## Fix 1: Active-first ordering is reversed

Current code:
```python
.order_by(
    PgPriority.status.desc(),  # 'retired' > 'active' so desc puts active first
    PgPriority.created_at.asc(),
)
```

The comment is wrong. `"active" < "retired"` alphabetically, so DESC puts retired first. This is a real behavioral bug — the widget receives retired priorities before active ones.

Fix:
```python
.order_by(
    PgPriority.status.asc(),  # 'active' < 'retired' alphabetically → active first
    PgPriority.created_at.asc(),
)
```

## Fix 2: avg_hours_week 0 becomes None

Current:
```python
priority_data["avg_hours_week"] = float(p.avg_hours_week) if p.avg_hours_week else None
```

Fix:
```python
priority_data["avg_hours_week"] = float(p.avg_hours_week) if p.avg_hours_week is not None else None
```

**Why:** `Decimal("0")` is falsy. A priority with zero average hours returns NULL to the widget instead of 0.0.

## Fix 3: weekly_hour_target 0 becomes None (consistency)

Current:
```python
"weekly_hour_target": float(p.weekly_hour_target) if p.weekly_hour_target else None,
```

Fix:
```python
"weekly_hour_target": float(p.weekly_hour_target) if p.weekly_hour_target is not None else None,
```

Same falsy pattern. Value of 0 is blocked by Pydantic validation today, but the conversion should be correct regardless.

## Fix 4: total_hours_invested same pattern (consistency)

Check the existing line for `total_hours_invested` in `build_priorities_response`. If it uses the falsy pattern, apply the same `is not None` fix. Current code appears to use `or 0.0` fallback which is fine, but verify.

## What NOT to do

- Do NOT change the query logic, keyword assignment, or concurrency handling
- Do NOT change any endpoint signatures or response shapes
- Do NOT touch deliverable endpoints

## Tests

- Any existing test that asserts priority ordering in the response should now expect active before retired. If no such test exists, add one to `test_priorities_router.py`:
  - Create one active and one retired priority, call `build_priorities_response`, assert active appears first in the list.
