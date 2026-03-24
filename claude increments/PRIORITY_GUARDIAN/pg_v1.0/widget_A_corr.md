# PG Widget Inc A — Design Corrections

These corrections override the original briefing where it conflicts with the locked widget spec (`pg-widget-spec-v1.md`).

---

## 1. Badge Colors: NO red/green/orange

**Locked design principle:** "No success/danger/warning colors on progress indicators." and "Neutral, distinguishable palette. No success/danger connotation."

**Current (wrong):** P1 = `success` (green), P2 = `warning` (orange), P3 = `danger` (red)

**Correct:** Use the neutral distinguishable palette from the widget spec:
- P1 = muted blue
- P2 = muted purple  
- P3 = muted teal

Do NOT use `<Badge color="success">`, `<Badge color="warning">`, or `<Badge color="danger">`.

Use `<Badge color="secondary">` with custom background colors via Tailwind classes or CSS custom properties:
```
P1: bg-[#5B8DEF] text-white  (muted blue)
P2: bg-[#9B7FD4] text-white  (muted purple)
P3: bg-[#4DB6AC] text-white  (muted teal)
```

Or define CSS custom properties and reference them. The exact hex values above are starting points — adjust for WCAG AA contrast on both light and dark themes.

---

## 2. Badge Placement: BEFORE the title, not after

**Locked spec:** "Header line: `[P1]` (colored) + priority name"

**Current (wrong):** Title on left, badge on right

**Correct:** Badge first, then title. Left-aligned together:
```
[P1] Build my business so that it achieves break even
```

Remove `justify-between` from header. Use `flex items-center gap-2` with badge first, then title.

---

## 3. Google Connection: Move to BOTTOM of widget

**Current (wrong):** Connection status header at the top

**Correct:** Google Calendar connect/disconnect section at the bottom, below all priority cards. It's a settings-level control, not primary content. Priorities are the primary content.

Use the SDK `Button` component. Keep the same connect/disconnect logic, just move the `<ConnectionStatus />` component to render after the priority cards section.

---

## 4. Deadline Card: Remove weekly hours display

**Locked spec data model:** Deadline priorities have `deadline` + `deliverables`. No `weeklyHourTarget`.

**Current (wrong):** Both card types show "Xh/week target (h actual)"

**Correct:**
- **Deadline cards:** Show "⏱ Deadline" + "[X] of [Y] done · [N]d left". NO weekly hours.
- **Flexible cards:** Show "↻ Flexible" + "Xh/week target" + checkpoint info. Weekly hours are flexible-only.

The `FlexibleCard` component's weekly hours display is correct in concept but should only render when `weeklyHourTarget` exists (which it should, since it's required for flexible). The `DeadlineCard` must not render any weekly hours fields at all — verify it doesn't.

Also fix: "(h actual)" shows as literal text when `weeklyHourActual` is undefined/0. Either hide actual hours entirely when not available, or show "0h actual". Don't show "(h actual)" as a label with no value.

---

## 5. Widget Centering: Fix desktop layout

**Current (wrong):** Widget content leans to the left side on desktop

**Correct:** The widget container should be horizontally centered. Check:
- `main.css`: `#root` has `max-width: 600px; margin: 0 auto` — this is correct
- `App.tsx`: The `<main>` element has `-m-4` (negative margin) which may be pulling it left. Remove `-m-4` or investigate why it was added.
- Check if `body` padding is asymmetric or if the ChatGPT sandbox iframe has alignment issues.

The fix is likely removing `-m-4` from the `<main>` element. If that creates padding issues, address them with proper `px` values instead of negative margins.

---

## 6. Backend: Reject cross-type fields on priority creation

**Problem:** `CreatePriorityRequest` in `backend/apps/priority_guardian/models/requests.py` validates that required fields exist per type, but does NOT reject fields that belong to the other type. A deadline priority can be created with `weekly_hour_target` set — it gets silently stored in the DB.

**Fix in `requests.py`:** Add rejection logic to `validate_type_conditional_fields`:

For `type == "deadline"`: reject if `weekly_hour_target`, `checkpoint_date`, or `desired_result` are provided. Raise `ValueError("weekly_hour_target is not valid for deadline priorities")` etc.

For `type == "flexible"`: reject if `deadline` is provided. Raise `ValueError("deadline is not valid for flexible priorities")`.

This is a Pydantic model_validator change — no router changes needed. Backend tests should cover both the "requires correct fields" and "rejects wrong fields" cases.

---

## Summary: Files to modify

| File | Changes |
|------|---------|
| `src/components/DeadlineCard.tsx` | Badge before title, neutral blue color, remove any weekly hours display |
| `src/components/FlexibleCard.tsx` | Badge before title, neutral purple color, fix "(h actual)" empty state |
| `src/components/ConnectionStatus.tsx` | No structural changes, just moved in App.tsx |
| `src/App.tsx` | Move `<ConnectionStatus />` below priority cards. Remove `-m-4`. |
| `backend/apps/priority_guardian/models/requests.py` | Reject cross-type fields in model_validator |

After widget changes: `npm run build` to regenerate `pg-dashboard.html`.