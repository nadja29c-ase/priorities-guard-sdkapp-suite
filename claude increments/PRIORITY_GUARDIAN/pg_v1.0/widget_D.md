# Widget Increment D: Dashboard V7 Redesign — Display Modes, Goal Arrays, Collapsible Sections

## Objective

Redesign the PG dashboard widget to match the V7 visual design with three specific enhancements:
1. **Colored left borders** on priority cards (P1 blue, P2 purple, P3 yellow)
2. **Collapsible sections**: deliverables always collapsible; 1-Month Goals collapsible only when 2-3 goals exist
3. **Inline/Fullscreen display modes**: same card components in both modes, different collapse defaults

After this increment: the dashboard supports `inline` (default) and `fullscreen` display modes via `window.openai.requestDisplayMode()`, flexible priorities support 1-3 goals with individual achievement toggles, and the visual design matches the approved V7 mockup.

**This is a cross-layer increment**: widget + MCP + backend + database migration.

---

## Design Reference

The approved V7 mockup is at: `mcp_server/priority_guardian/widgets/pg-dashboard-v7-tweaked.jsx`

Copy it from `/mnt/user-data/outputs/pg-dashboard-v7-tweaked.jsx` into the widgets directory if it's not there already. This file is the **visual source of truth** — match its layout, spacing, colors, and component structure exactly. It uses Tailwind classes and CSS custom properties from the OpenAI SDK design token system.

**Important**: The mockup uses hardcoded Tailwind color classes (e.g., `bg-blue-500`, `bg-purple-50`) for rapid prototyping. The production widget MUST use OpenAI SDK semantic tokens instead (e.g., `bg-info-solid`, `bg-discovery-soft-alpha`). The mockup's inline CSS `var()` fallbacks (e.g., `var(--gray-900, #181818)`) are the correct production approach.

---

## Data Model Change: `desired_result` → `pg_goals` table

### Current State

`desired_result` is a single `String(200)` column on `pg_priorities`. It flows through:
- **DB**: `PgPriority.desired_result` — `String(200), nullable`
- **Backend router**: `build_priorities_response()` serializes as `"desired_result": p.desired_result`
- **Request models**: `CreatePriorityRequest.desired_result` and `UpdatePriorityRequest.desired_result` — both `Optional[str]`
- **MCP normalization**: `_normalize_priority()` maps to `"desiredResult": p.get("desired_result")`
- **Widget types**: `Priority.desiredResult?: string`

### Target State

A new `pg_goals` table — child of `pg_priorities`, same relationship pattern as `pg_deliverables`.

### Why a table, not JSONB

This is a deliberate architectural choice: `pg_goals` mirrors the existing `pg_deliverables` pattern exactly. Same parent-child FK relationship, same CRUD operations, same MCP tool structure, same widget interaction. This means every layer (db model, router, request models, MCP tools, widget components) can be built by copying and renaming the existing deliverables infrastructure. Zero new patterns needed.

### Migration Strategy

**Database migration** (Alembic):
1. Create `pg_goals` table
2. Data migration: for each row where `desired_result IS NOT NULL`, insert one row into `pg_goals` with `text = desired_result, achieved = false`
3. Drop `desired_result` column from `pg_priorities`

**Backward compatibility**: Breaking schema change. All layers deployed together. No transition period needed (pre-launch, no external consumers).

---

## Layer 1: Backend Changes

### Files to Create

| File | Purpose |
|------|---------|
| None — the goal model goes into the existing `db_models.py` | |

### Files to Modify

| File | Change |
|------|--------|
| `backend/apps/priority_guardian/db_models.py` | Add `PgGoal` model (copy `PgDeliverable`, rename), add relationship to `PgPriority`, remove `desired_result` column |
| `backend/apps/priority_guardian/models/requests.py` | Add `CreateGoalRequest`, `UpdateGoalRequest` (copy deliverable request models), update `CreatePriorityRequest` and `UpdatePriorityRequest` to remove `desired_result` |
| `backend/apps/priority_guardian/routers/priorities_router.py` | Add goal CRUD endpoints, update `build_priorities_response()` to serialize goals, remove `desired_result` serialization |

### db_models.py

**Add `PgGoal` — copy `PgDeliverable` and adapt:**

| PgDeliverable field | PgGoal equivalent |
|---|---|
| `id` (UUID PK) | Same |
| `priority_id` (FK to pg_priorities) | Same |
| `name` (String 200) | `text` (String 200) — the goal text |
| `done` (Boolean) | `achieved` (Boolean, default false) |
| `created_at` | Same |
| `updated_at` | Same |

**Add constraint**: max 3 goals per priority. Use a check constraint or enforce in the router (same way max 3 priorities is enforced — router-level check before insert).

**Add relationship on PgPriority:**
```
goals: Mapped[list["PgGoal"]] = relationship("PgGoal", back_populates="priority", cascade="all, delete-orphan", lazy="selectin")
```

**Remove**: `desired_result` column from `PgPriority`.

### models/requests.py

**Add `CreateGoalRequest`** — copy `CreateDeliverableRequest`:
- `text: str` (min 1, max 200, non-empty validation) — replaces `name`

**Add `UpdateGoalRequest`** — copy `UpdateDeliverableRequest`:
- `text: Optional[str]` (max 200)
- `achieved: Optional[bool]`

**Update `CreatePriorityRequest`:**
- Remove `desired_result` field
- Remove validation of `desired_result` for flexible type
- Note: goal creation happens AFTER priority creation (separate endpoint), same as deliverables. The onboarding conversation or AddPriorityForm creates the priority first, then adds the initial goal.

**Update `UpdatePriorityRequest`:**
- Remove `desired_result` field

### priorities_router.py

**Add goal CRUD endpoints — copy the deliverable endpoints and rename:**

| Deliverable endpoint | Goal equivalent |
|---|---|
| `POST /priorities/{id}/deliverables` | `POST /priorities/{id}/goals` |
| `PUT /priorities/{id}/deliverables/{did}` | `PUT /priorities/{id}/goals/{gid}` |
| `DELETE /priorities/{id}/deliverables/{did}` | `DELETE /priorities/{id}/goals/{gid}` |

All follow the same pattern: validate ownership → perform operation → return `build_priorities_response()`.

**Add to goal creation endpoint**: enforce max 3 goals per priority (count existing goals, reject if >= 3).

**Update `build_priorities_response()`:**
- Remove `"desired_result": p.desired_result`
- Add goals serialization (same pattern as deliverables):
  ```python
  goals_data = [{"id": str(g.id), "text": g.text, "achieved": g.achieved} for g in p.goals]
  priority_data["goals"] = goals_data
  ```

---

## Layer 2: MCP Changes

### Files to Create

| File | Purpose |
|------|---------|
| `tools/widget_tools/add_goal.py` | Copy `add_deliverable.py`, rename for goals |
| `tools/widget_tools/update_goal.py` | Copy `update_deliverable.py`, rename for goals |
| `tools/widget_tools/delete_goal.py` | Copy `delete_deliverable.py`, rename for goals |

### Files to Modify

| File | Change |
|------|--------|
| `tools/get_priorities.py` | Update `_normalize_priority()` to map `goals` instead of `desired_result` |
| `tools/widget_tools/update_priority.py` | Remove `desired_result` from input schema |
| `tools/widget_tools/__init__.py` | Register new goal tools |

### New goal tools — copy existing deliverable tools and rename:

| Deliverable tool | Goal tool | Differences |
|---|---|---|
| `add_deliverable.py` | `add_goal.py` | Endpoint: `/priorities/{id}/goals`, field: `text` instead of `name` |
| `update_deliverable.py` | `update_goal.py` | Endpoint: `/priorities/{id}/goals/{gid}`, fields: `text` and `achieved` instead of `name` and `done` |
| `delete_deliverable.py` | `delete_goal.py` | Endpoint: `/priorities/{id}/goals/{gid}` |

All use the same response pattern: return structuredContent with full priorities list and widget URI.

### get_priorities.py

**`_normalize_priority()`:**
- Remove: `"desiredResult": p.get("desired_result")`
- Add: normalize goals array (same pattern as deliverables normalization):
  ```python
  goals = p.get("goals", [])
  normalized_goals = [{"id": g.get("id"), "text": g.get("text"), "achieved": g.get("achieved", False)} for g in goals]
  result["goals"] = normalized_goals
  ```

### update_priority.py

- Remove `desired_result` from input schema properties
- Remove `desired_result` handling from handler payload building

---

## Layer 3: Widget Changes

### Files to Create

| File | Purpose |
|------|---------|
| `src/components/GoalSection.tsx` | Conditional collapsibility, goal achievement toggles |
| `src/components/GoalItem.tsx` | Single goal row with circular checkbox |
| `src/components/CalendarConnectionMinimal.tsx` | Minimal "connected" indicator for inline mode |
| `src/components/FullscreenHeader.tsx` | "My Priorities" title + Minimize button |
| `src/components/ExpandButton.tsx` | "Open full dashboard" button for inline mode |

### Files to Modify

| File | Change |
|------|--------|
| `src/types.ts` | Add `Goal` interface, update `Priority` interface, add `DisplayMode` type |
| `src/constants.ts` | Add `BORDER_COLORS` mapping for card left borders (reuse existing color values from `RING_STROKE_COLORS`) |
| `src/App.tsx` | Add display mode state, toggle goal handler, conditional rendering, extend existing `set_globals` listener |
| `src/components/DeadlineCard.tsx` | Add colored left border, collapsible deliverables section |
| `src/components/FlexibleCard.tsx` | Add colored left border, replace goal section with GoalSection component, update edit mode for goals |
| `src/components/AddPriorityForm.tsx` | Change `desired_result` (single string) to `desired_results` (array of strings) for flexible priority creation |

### types.ts Changes

Add:
```typescript
export type DisplayMode = 'inline' | 'fullscreen'

export interface Goal {
  id: string
  text: string
  achieved: boolean
}
```

Update `Priority` interface:
- Remove: `desiredResult?: string`
- Add: `goals: Goal[]` (always present, can be empty array for deadline priorities)

### constants.ts Changes

Add card left border colors as inline style values (not Tailwind classes), matching the V7 mockup's `KEYWORD_STYLES.borderColor`:

```
BORDER_COLORS: { P1: '#0285ff', P2: '#924ff7', P3: '#ffc300' }
```

Applied via inline `borderLeft` style on card `<article>` elements.

### App.tsx Changes

**New state:**
- `displayMode`: Initialize from `window.openai?.displayMode ?? 'inline'`. Only treat `'fullscreen'` as fullscreen; everything else (including `'pip'`) maps to `'inline'` behavior.

**Display mode listener — EXTEND existing handler, don't duplicate:**
- App.tsx already has a `handleSetGlobals` listener (in the `useEffect` that calls `loadData()`). Extend this existing listener to also read `window.openai?.displayMode` and update the `displayMode` state. Do NOT create a second `openai:set_globals` listener.

**New CRUD handler — `handleToggleGoal(goalId, achieved)`:**
- Follow the EXACT pattern of `handleToggleDeliverable` in App.tsx — same `callTool → extractStructuredContent → updateDataFromResponse → error handling` flow. The only differences: tool name is `'update_goal'`, args are `{ goal_id: goalId, achieved: achieved }`.
- Preserve `timeAllocation` across CRUD (same as existing pattern — already handled by `updateDataFromResponse`).

**New CRUD handlers for goal management (copy deliverable handlers):**
- `handleAddGoal(priorityId, text)` — copies `handleAddDeliverable`, calls `'add_goal'` tool
- `handleUpdateGoal(goalId, updates)` — copies `handleRenameDeliverable`, calls `'update_goal'` tool
- `handleDeleteGoal(goalId)` — copies `handleDeleteDeliverable`, calls `'delete_goal'` tool

**Update existing `handleAddPriority`:**
- Remove `desired_result` field from the payload sent to `add_priority` tool.

**Update existing `handleUpdatePriority`:**
- Remove `desired_result` from accepted updates (goal editing is now via dedicated goal tools).

**Display mode switching:**
- `handleExpandToFullscreen()`: calls `window.openai?.requestDisplayMode?.({ mode: 'fullscreen' }).catch(() => {})` then sets local state. The `.catch()` is required — `requestDisplayMode` may reject (e.g., host doesn't support fullscreen).
- `handleMinimizeToInline()`: calls `window.openai?.requestDisplayMode?.({ mode: 'inline' }).catch(() => {})` then sets local state.

**Conditional rendering based on `displayMode`:**

| Element | Inline | Fullscreen |
|---------|--------|------------|
| FullscreenHeader | hidden | visible |
| TimeAllocationBar | visible (same) | visible (same) |
| DeadlineCard `defaultDeliverablesExpanded` | `false` | `true` |
| FlexibleCard `defaultGoalExpanded` | `false` | `true` |
| AddPriorityForm/Button | visible (same) | visible (same) |
| CalendarConnectionMinimal | visible | hidden |
| ConnectionStatus (full) | hidden | visible |
| ExpandButton | visible | hidden |

**Card key strategy**: Use `key={\`${priority.id}-${displayMode}\`}` on DeadlineCard and FlexibleCard to force remount when display mode changes. This ensures collapse state resets to the mode's default.

**Update `PriorityCardWrapper`**: This component (in App.tsx) wires props to DeadlineCard and FlexibleCard. It must be updated to:
- Pass `defaultDeliverablesExpanded={!isInline}` to DeadlineCard
- Pass `defaultGoalExpanded={!isInline}` and `onToggleGoal` to FlexibleCard
- Pass the display-mode-aware `key` prop

### DeadlineCard.tsx Changes

**New props:**
- `defaultDeliverablesExpanded: boolean` (from App based on display mode)

**Colored left border:**
- Card `<article>` gets `borderLeft: 4px solid ${BORDER_COLORS[priority.calendarKeyword]}`
- The card already has `border border-default` — the left border overrides just the left side

**Collapsible deliverables:**
- Add `deliverablesExpanded` state initialized from `defaultDeliverablesExpanded`
- Section header becomes a clickable button with:
  - "E2E DELIVERABLES" label (uppercase, xs, tracking-wide)
  - Count badge: `(done/total)` in secondary color
  - Chevron icon (rotates 180° when expanded, 150ms ease-out transition)
- When collapsed: only header visible
- When expanded: full checklist + "Add deliverable" button (existing behavior)

**V7 visual changes (match mockup exactly):**
- Deadline banner: colored background using `accentSoft` token for the keyword. Contains calendar icon + deadline date (left) and days remaining (right)
- Lead measure: large `done/total` number with "deliverables done" label below
- Badge: circular (w-6 h-6 rounded-full) with keyword text, using keyword-specific badge colors

### FlexibleCard.tsx Changes

**New props:**
- `defaultGoalExpanded: boolean` (from App based on display mode)
- `onToggleGoal: (priorityId: string, goalId: string) => Promise<void>`

**Colored left border:** Same approach as DeadlineCard.

**Replace 1-Month Goal section** (the existing `!isEditing && priority.desiredResult` block, ~lines 290-305) with `<GoalSection>` component (see below). The existing section is a simple text display — GoalSection replaces it with conditional collapsibility and achievement toggles.

**Update edit mode for goals:**
- The existing edit mode has a `desiredResult` textarea with `editDesiredResult` state and `handleDesiredResultBlur` auto-save. This needs to change to support 1-3 goal text fields instead of a single textarea.
- The `autoSave` function currently sends `desired_result` — goal editing now uses dedicated goal CRUD tools (`add_goal`, `update_goal`, `delete_goal`) instead of the priority update tool. Follow the same pattern as deliverable editing.
- The `useEffect` that resets local state from props currently reads `priority.desiredResult` — must change to `priority.goals`.

**V7 visual changes (match mockup exactly):**
- Streak shown as pill: `"{count}w streak"` in neutral gray pill next to name (replaces current 🔥 emoji display)
- HourRing next to avg target achievement stat
- If `avgTargetAchievement` is not null: show `~{rounded}%` large number with "of weekly target on avg" label
- If null (< 2 data points): show "Building your average…" in gray

### GoalSection Component

**Props:**
```typescript
{
  priority: Priority
  onToggleGoal: (priorityId: string, goalId: string) => Promise<void>
  defaultExpanded?: boolean  // default: true
}
```

**Behavior:**

Read `priority.goals` (array). Determine `isCollapsible = goals.length > 1`.

**Single goal (1 goal):**
- Header: `"1-MONTH GOAL"` (uppercase) + `"by {checkpointDate} · {days}d to check-in"` (secondary text)
- Header is NOT clickable, no chevron
- Goal always visible below header
- Rendered via GoalItem component

**Multiple goals (2-3 goals):**
- Header: clickable button with `"1-MONTH GOALS"` (plural) + `"({achieved}/{total})"` count + `"· by {checkpointDate} · {days}d to check-in"` + chevron
- Toggle `expanded` state on click
- Goals visible only when expanded
- Each rendered via GoalItem component

**Collapse state**: Initialized from `defaultExpanded` prop. Resets on remount (via key strategy in App.tsx).

**Separator**: The goal section has a top border separator (`border-top: 1px solid var(--gray-75)`).

### GoalItem Component

**Structural reference: `DeliverableItem.tsx`** — GoalItem follows the same interaction pattern (checkbox + text + toggle + visual state change on completion). Use DeliverableItem as the blueprint. The differences are:
- **Checkbox shape**: circular (18px rounded-full) instead of square (16px rounded)
- **Checked color**: green fill (`--green-500`) instead of gray (`--gray-200`)
- **Toggle action**: calls `onToggle(goalId)` instead of `onToggle(deliverableId, done)`
- **No hover edit/delete actions** (goals are edited via the priority edit mode, not individually)

**Props:**
```typescript
{
  goal: Goal
  onToggle: (goalId: string) => void
}
```

**Renders:**
- Circular checkbox (18px diameter):
  - Not achieved: 1.5px border in `--gray-300`, transparent background
  - Achieved: green background (`--green-500`), white checkmark SVG
  - 150ms transition on all properties
- Goal text:
  - Not achieved: `text-sm`, color `--gray-700`
  - Achieved: `text-sm`, `line-through`, color `--gray-350`
- Click on checkbox calls `onToggle(goal.id)`

### CalendarConnectionMinimal Component

Minimal indicator for inline mode. Shows only when Google Calendar is connected.

**Renders:**
- Small green dot (w-1.5 h-1.5, `--green-500`) + "Google Calendar connected" text (xs, `--gray-400`)
- If not connected: don't render this component (the full ConnectionStatus in fullscreen handles the connect flow)

### FullscreenHeader Component

**Props:** `{ onMinimize: () => void }`

**Renders:**
- "My Priorities" title (sm, font-semibold, `--gray-900`)
- "Minimize" button (xs, `--gray-500`, no border, hover bg-gray-100)
- Bottom border separator
- Calls `onMinimize` which triggers `requestDisplayMode({ mode: 'inline' })`

### ExpandButton Component

**Props:** `{ onExpand: () => void }`

**Renders:**
- Full-width button with "Open full dashboard" text + right chevron icon
- Color: `--blue-500` text on `--blue-50` background
- Rounded-xl, py-2.5
- Calls `onExpand` which triggers `requestDisplayMode({ mode: 'fullscreen' })`

### AddPriorityForm.tsx Changes

The existing form sends `desired_result` as a single string for flexible priorities. With the table-based approach, goal creation is a separate operation from priority creation (same as deliverables).

**Current state:**
- `desiredResult` state (single string), single textarea field
- `handleSubmit` sends `desired_result: desiredResult` to `onAdd`
- Validation checks `desiredResult` is non-empty for flexible type

**Target state:**
- Keep the single textarea for goal text input during priority creation
- `handleSubmit` creates the priority first (without `desired_result`), then immediately calls `add_goal` with the goal text
- This is the same two-step pattern that would apply if deliverables were created during priority creation
- Remove `desired_result` from the `onAdd` callback type signature
- Add a new `onAddGoal: (priorityId: string, text: string) => Promise<void>` prop (follows same pattern as `onAddDeliverable`)

**Alternative (simpler):** If two sequential tool calls feel fragile, keep goal creation as part of the priority creation flow by having the backend `POST /priorities` endpoint accept an optional `initial_goal_text` field that creates both the priority and its first goal in one transaction. This avoids the widget needing to chain two calls. Decide based on what feels more robust.

**Rationale:** Users start with one goal and can add more later via edit mode. Multi-goal creation form is unnecessary complexity for initial creation.

---

## Widget State Persistence

Add `displayMode` to widget state. When display mode changes, persist via `setWidgetState` so it survives re-renders:

```typescript
window.openai?.setWidgetState?.({
  ...existingState,
  displayMode: newMode,
  editingPriorityId: existingState.editingPriorityId,
  addFormOpen: existingState.addFormOpen,
})
```

On initialization, read from `widgetState?.displayMode` as fallback if `window.openai.displayMode` is undefined.

**Host always wins**: If `window.openai.displayMode` has a value, it takes precedence over persisted widgetState. The widget must never fight the host's display mode. The `openai:set_globals` listener updates local state to match the host at all times.

---

## Design Tokens Reference (for V7 compliance)

All colors must use CSS custom properties with fallbacks. **Hard rule: No raw Tailwind color classes in production code.** Specifically prohibited: `bg-blue-*`, `text-purple-*`, `bg-yellow-*`, `text-green-*`, or any Tailwind color utility that isn't an OpenAI SDK semantic token. The V7 mockup uses these for prototyping — they must be replaced with SDK tokens or inline CSS variables in production.

**Card left borders (inline style, not Tailwind):**
- P1: `#0285ff` (--blue-400)
- P2: `#924ff7` (--purple-400)
- P3: `#ffc300` (--yellow-400)

**Badge colors (existing in constants.ts as BADGE_COLORS):**
- P1: `bg-info-soft-alpha text-info` (blue)
- P2: `bg-discovery-soft-alpha text-discovery` (purple)
- P3: `bg-caution-soft-alpha text-caution` (yellow)

**Deadline banner background:**
- Use the keyword's `accentSoft` color — apply via inline style using CSS variable with fallback
- P1: `var(--color-background-info-soft-alpha)` fallback `#eff6ff`
- P2: `var(--color-background-discovery-soft-alpha)` fallback `#faf5ff`
- P3: `var(--color-background-caution-soft-alpha)` fallback `#fefce8`

**Text hierarchy:**
- Primary text: `var(--gray-900, #181818)`
- Secondary text: `var(--gray-500, #5d5d5d)`
- Tertiary/muted: `var(--gray-400, #8f8f8f)` or `var(--gray-350, #9f9f9f)`
- Disabled/placeholder: `var(--gray-450, #767676)`

**Borders/separators:**
- Card border: `1px solid var(--gray-100, #ededed)`
- Internal separator: `1px solid var(--gray-75, #f3f3f3)`

**Goal achievement checkbox:**
- Unchecked: border `var(--gray-300, #afafaf)`, transparent fill
- Checked: fill `var(--green-500, #00a240)`, white checkmark

**Spacing (consistent throughout):**
- Card padding: `p-5` (20px)
- Card gap: `gap-3` (12px between cards)
- Section gap within card: `mb-3`, `mb-4`
- Time bar to cards: `mb-5`

---

## Unit Tests

### Widget Tests

**File:** `src/__tests__/GoalSection.test.tsx`

Framework: Vitest + React Testing Library (existing setup in project).

**Rendering tests:**
- Single goal: renders header as non-clickable, no chevron visible, goal always visible
- Single goal: header says "1-MONTH GOAL" (singular)
- Multiple goals (2): renders clickable header with chevron, says "1-MONTH GOALS" (plural)
- Multiple goals: shows achievement count "(1/2)" in header
- Checkpoint date and days displayed correctly

**Collapse behavior:**
- Multiple goals, `defaultExpanded=true`: goals visible on mount
- Multiple goals, `defaultExpanded=false`: goals hidden on mount
- Multiple goals: clicking header toggles visibility
- Single goal: always visible regardless of `defaultExpanded`

**GoalItem tests:**
- Unchecked goal: shows empty circle, normal text
- Checked goal: shows green circle with checkmark, strikethrough text
- Click calls `onToggle` with correct `goalId`

**File:** `src/__tests__/DeadlineCard.test.tsx`

- Deliverables collapsed when `defaultDeliverablesExpanded=false`: checklist hidden, count shows in header
- Deliverables expanded when `defaultDeliverablesExpanded=true`: checklist visible
- Clicking deliverables header toggles visibility
- Colored left border present with correct color for keyword

**File:** `src/__tests__/DisplayMode.test.tsx`

- Inline mode: ExpandButton visible, FullscreenHeader hidden, CalendarConnectionMinimal visible
- Fullscreen mode: ExpandButton hidden, FullscreenHeader visible, full ConnectionStatus visible
- Display mode switch: clicking "Open full dashboard" calls `requestDisplayMode`

### Backend Tests

**File:** `backend/tests/test_goal_crud.py` (or wherever backend tests live)

Copy test structure from deliverable CRUD tests and rename.

- Add goal to flexible priority: success
- Add goal to deadline priority: validation error (only flexible priorities have goals)
- Add 4th goal to priority with 3 goals: max limit error
- Add goal with empty text: validation error
- Add goal with >200 char text: validation error
- Update goal text: success
- Update goal achieved status: success (toggle)
- Delete goal: success
- Add/update/delete goal on another user's priority: 403/404
- Goal cascades on priority delete: verify goals deleted when priority deleted
- Verify response includes full priority list with goals array

---

## Integration Tests

**MCP integration (manual or automated):**
- Call `get_priorities` → verify `goals` array in response for flexible priorities
- Call `add_goal` → verify goal added to priority
- Call `update_goal` with `achieved: true` → verify single goal toggled, others unchanged
- Call `update_goal` with `text: "new text"` → verify goal text updated
- Call `delete_goal` → verify goal removed
- Call `add_goal` when priority already has 3 goals → verify error response (max 3)

**Widget E2E (manual via MCP Inspector + browser):**
- Load dashboard in inline mode → deliverables collapsed, multi-goals collapsed, single goals expanded
- Click "Open full dashboard" → mode switches, deliverables expand, multi-goals expand
- Click goal checkbox → achievement toggles (visual + persisted)
- Click "Minimize" in fullscreen header → returns to inline mode with correct collapse states

---

## Database Migration

**Migration file**: Alembic auto-generate will create the `pg_goals` table. The data migration (moving existing `desired_result` values) must be added manually.

**Steps:**
1. Create `pg_goals` table (auto-generated from model)
2. Execute data migration SQL:
   ```sql
   INSERT INTO pg_goals (id, priority_id, text, achieved, created_at, updated_at)
   SELECT gen_random_uuid(), id, desired_result, false, now(), now()
   FROM pg_priorities
   WHERE desired_result IS NOT NULL;
   ```
3. `op.drop_column('pg_priorities', 'desired_result')`

**Downgrade** (for rollback):
1. Add back `desired_result` column on `pg_priorities`
2. Copy first goal text back: `UPDATE pg_priorities SET desired_result = (SELECT text FROM pg_goals WHERE pg_goals.priority_id = pg_priorities.id LIMIT 1)`
3. Drop `pg_goals` table

---

## What This Increment Does NOT Include

- Weekly report integration with goals (future increment)
- Goal reordering within a priority
- Multi-goal creation form (users create one goal at priority creation, add more via edit mode)
- Animations on display mode transition (CSS transitions on collapse/expand are included)
- PiP display mode support (maps to inline behavior)
- Responsive breakpoints for different screen widths (widget already max-width constrained)

---

## Deployment Order

All layers must be deployed together (breaking schema change):

1. **Database migration** (run Alembic)
2. **Backend** (deploy with new router + model changes)
3. **MCP server** (deploy with new tool + normalization changes)
4. **Widget** (build + deploy HTML bundle)

---

## Validation Criteria (Definition of Done)

### Backend
1. `pg_goals` table exists with FK to `pg_priorities`, cascade delete
2. Data migration preserves existing `desired_result` values as single goal rows
3. `desired_result` column removed from `pg_priorities`
4. Goal CRUD endpoints work (add, update, delete) with ownership validation
5. Max 3 goals per priority enforced
6. All mutation endpoints return full priority list with `goals` array

### MCP
7. `get_priorities` returns `goals` array (not `desiredResult` string)
8. Goal CRUD tools registered and functional (`add_goal`, `update_goal`, `delete_goal`)
9. `update_priority` no longer accepts `desired_result`
10. All responses include correct widget URI

### Widget
10. Cards have colored left borders matching keyword (P1 blue, P2 purple, P3 yellow)
11. Deliverables section collapsible with chevron + count badge
12. GoalSection: single goal always visible (no chevron); 2-3 goals collapsible
13. GoalItem: circular checkbox toggles achievement (green/white when achieved)
14. Inline mode: deliverables collapsed, multi-goals collapsed, CalendarConnectionMinimal, ExpandButton visible
15. Fullscreen mode: everything expanded, FullscreenHeader with Minimize, full ConnectionStatus
16. Display mode switch works via `requestDisplayMode` API
17. Card remount on mode switch resets collapse state
18. CRUD operations preserve `timeAllocation` (not cleared)
19. Widget builds without errors (`npm run build`)
20. Correct rendering in both light and dark themes
21. All unit tests pass