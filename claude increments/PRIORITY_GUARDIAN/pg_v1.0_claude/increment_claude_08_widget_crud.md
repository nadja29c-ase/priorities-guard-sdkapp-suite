# Increment Claude-08: Claude-Native Interactive Widget — Fullscreen CRUD

**Updated:** May 2026 — reflects Anthropic design guidelines and ChatGPT review feedback

**Goal:** Upgrade the Claude widget from display-only to full interactive CRUD using the MCP Apps `@modelcontextprotocol/ext-apps` bridge. Architecture: inline card is read-only and Anthropic-compliant; fullscreen exposes full CRUD.

---

## Context

The Claude widget (Increment Claude-06) is display-only with 8 components. The ChatGPT widget has 17 components and full CRUD. `callServerTool` is confirmed working in `ext-apps` v1.7.1.

**Why not a 1:1 copy of the ChatGPT widget:**

Anthropic publishes design constraints at `claude.com/docs/connectors/building/mcp-apps/design-guidelines` that differ from ChatGPT's. The ChatGPT inline card violates these constraints.

| Inline card constraint | ChatGPT widget | Claude widget (required) |
|---|---|---|
| Max height | No limit | 500px auto-fit |
| Max actions | No limit | 2 total |
| Menus/popovers | `KeywordPicker` dropdown | Not allowed inline |
| Nested scrolling | Present | Not allowed |

**Inline action budget — at most 2:**
1. `ExpandButton` — opens fullscreen (always shown)
2. `CalendarConnectionMinimal` connect/disconnect button — only if connection action is needed

If `CalendarConnectionMinimal` shows no action button, inline has 1 action total. No additional actions in any case. "Optional quick action" was in a previous draft — removed.

**Solution: inline/fullscreen split**

- **Inline:** Read-only summary. Priorities with key stats. TimeAllocationBar (no refresh). Max 2 actions. No dropdowns. Auto-fit height ≤500px.
- **Fullscreen:** All CRUD. Edit/add/delete priorities, deliverables, goals. KeywordPicker. Delete confirmation. AddPriorityForm. ConnectionStatus. Fullscreen preserves ChatGPT widget functionality and visual language, adapted to Claude host constraints.

This is consistent with all current Connectors Directory interactive connectors — none expose delete affordances in the inline card.

**`allEvents` decision required before semantic grouping implementation:**

The structural guideline (`structural_guideline_claude_vs_openai.md`, Token Size Risk section) identifies `allEvents` inside `structuredContent` as wrong placement — it enters model context and risks token bloat for busy-calendar users. The semantic grouping feature (event-level weekly report interaction) depends on the model seeing `allEvents`. **Before implementing semantic grouping or event-level weekly report interaction, decide:** keep `allEvents` in `structuredContent` with a hard cap (pragmatic), or move to `_meta` and redesign semantic grouping (architecturally correct). PieChart display rendering does not require this decision and can be implemented now. Do not implement semantic grouping interaction until the decision is made and documented.

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting.

**Read these before writing any code:**

ChatGPT widget source (business logic and visual reference):
- `mcp_server/priority_guardian/widget-react/src/App.tsx` — 994 lines, primary reference
- `mcp_server/priority_guardian/widget-react/src/components/AddPriorityForm.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/AddDeliverableInput.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/DeleteConfirmation.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/KeywordPicker.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/ConnectionStatus.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/CalendarConnectionMinimal.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/PieChart.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/ExpandButton.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/FullscreenHeader.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/DeadlineCard.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx`

Compliance:
- `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md` — section "Anthropic Widget Design Constraints"

**MANDATORY BEFORE WRITING ANY BRIDGE CALLS:**

Inspect the installed `@modelcontextprotocol/ext-apps` TypeScript types:
```
mcp_server/priority_guardian_claude/widget-react/node_modules/@modelcontextprotocol/ext-apps/
```
Read the exported types and available methods on the `App` class. The bridge method names in this briefing (e.g. `callServerTool`, `getHostContext`, `onhostcontextchanged`, `notifyIntrinsicHeight`, `requestDisplayMode`, `setState`, `getState`, `openLink`) are based on research and the existing Claude widget implementation — but the installed version is authoritative. Replace any method name in this briefing with the actual exported name if they differ. Do not implement guessed bridge calls.

---

## Implementation Approach

**Preserve business logic and visual language. Adapt interaction density by display mode.**

The ChatGPT widget's component logic, data handling, state management, error handling, and visual structure are correct. Copy them directly. The adaptation required is:
1. Bridge API: `window.openai.*` → `app.*` (verify names against installed types)
2. Interaction density: CRUD surfaced in fullscreen only, not inline
3. Removal of ChatGPT-specific APIs that have no Claude equivalent (use feature detection where unsure)

Do not change component internals unless required for bridge compatibility or inline/fullscreen placement.

---

## Bridge API Translation

The table below maps ChatGPT bridge calls to their MCP Apps equivalents based on research and the existing Claude widget. **Verify all method names against installed TypeScript types before implementing.**

| ChatGPT (`window.openai.*`) | Expected Claude (`app.*`) | Verify |
|---|---|---|
| `window.openai.toolOutput` | `result.structuredContent` via `app.ontoolresult` | Already implemented — confirmed |
| `window.openai.callTool(name, args)` | `app.callServerTool({ name, arguments: args })` | Verify signature |
| `window.openai.setWidgetState(state)` | `app.setState(state)` | Verify name |
| `window.openai.widgetState` | `app.getState()` | Verify name |
| `window.openai.displayMode` | `app.getHostContext().displayMode` | Verify `getHostContext` name |
| `window.openai.requestDisplayMode({mode})` | `app.requestDisplayMode({mode})` | Verify name |
| `window.openai.notifyIntrinsicHeight()` | `app.notifyIntrinsicHeight()` | Verify name |
| `window.openai.locale` | `app.getHostContext().locale` | Verify field |
| `window.openai.userAgent` | `app.getHostContext().userAgent` | Verify field |
| `window.openai.safeArea` | `app.getHostContext().safeArea` | Verify field |
| `openai:set_globals` event | `app.onhostcontextchanged` callback | Verify callback name |
| `window.openai.openExternal({href})` | `app.openLink(url)` | Verify — may differ |

If a method does not exist in the installed types, use feature detection before calling:
```typescript
if (typeof appRef.current?.notifyIntrinsicHeight === 'function') {
  appRef.current.notifyIntrinsicHeight()
}
```

**Store `app` in a ref** — available only inside `onAppCreated` but needed in callbacks:
```typescript
const appRef = useRef<McpApp | null>(null)
// In onAppCreated: appRef.current = appInstance
```

**`callServerTool` expected return shape:**
```typescript
const result = await appRef.current.callServerTool<{ data?: ToolOutputData }>({
  name: 'add_priority',
  arguments: { name, type, ... }
})
const content = result?.structuredContent as { data?: ToolOutputData }
```

---

## What Gets Built

### New components (9 files)

Copy from `priority_guardian/widget-react/src/components/`. Translate bridge calls using verified method names. Do not change visual structure.

| File | Bridge changes | Display context |
|---|---|---|
| `AddPriorityForm.tsx` | None | Fullscreen only |
| `AddDeliverableInput.tsx` | None | Fullscreen only |
| `DeleteConfirmation.tsx` | None | Fullscreen only |
| `KeywordPicker.tsx` | None | Fullscreen only |
| `ExpandButton.tsx` | None | Inline only |
| `FullscreenHeader.tsx` | None | Fullscreen only |
| `CalendarConnectionMinimal.tsx` | Replace `openExternal` with verified `app` equivalent if present | Inline only |
| `ConnectionStatus.tsx` | Replace `callTool` with `appRef.current?.callServerTool` | Fullscreen only |
| `PieChart.tsx` | None | Both modes |

### Updated components (existing files — add CRUD props)

**`DeadlineCard.tsx`** — copy ChatGPT version's full prop interface:
- `onStartEdit`, `onCancelEdit`, `onSave`, `onDelete`, `onKeywordChange`
- `onToggleDeliverable`, `onRenameDeliverable`, `onDeleteDeliverable`, `onAddDeliverable`
- `isEditing`, `canStartEdit`, `priorities`
- `isInline: boolean` — when `true`, render display-only (no CRUD buttons, no edit state)

**`FlexibleCard.tsx`** — copy ChatGPT version's full prop interface:
- `onStartEdit`, `onCancelEdit`, `onSave`, `onDelete`, `onKeywordChange`
- `onAddGoal`, `onToggleGoal`, `onRenameGoal`, `onDeleteGoal`
- `isEditing`, `canStartEdit`, `priorities`
- `isInline: boolean` — same rule

**`TimeAllocationBar.tsx`** — add `onRefresh` and `isRefreshing` props. Copy from ChatGPT source. Refresh button hidden when `isInline=true`.

**`DeliverableItem.tsx`** — add `onToggle`, `onRename`, `onDelete`. Disabled when `isInline=true`.

**`GoalItem.tsx`** — add `onToggle`, `onRename`, `onDelete`. Disabled when `isInline=true`.

**`GoalSection.tsx`** — add `onAddGoal`, `onToggleGoal`, `onRenameGoal`, `onDeleteGoal`.

---

## `App.tsx` — Full Rewrite

Copy ChatGPT `App.tsx` logic, translate bridge API, apply inline/fullscreen split.

### Layout architecture

```
Inline (isInline=true):
  [TimeAllocationBar — no refresh button]
  [Priority summary cards — isInline=true, display-only]
  [CalendarConnectionMinimal]     ← action 1 (if connect button shown)
  [ExpandButton]                  ← action 2
  MAX 2 ACTIONS — no others
  MAX 500px — call notifyIntrinsicHeight() on every height change
  NO dropdowns, NO popovers, NO nested scroll

Fullscreen (isInline=false):
  [FullscreenHeader with minimize button]
  [TimeAllocationBar — with refresh button]
  [Priority cards — isInline=false, full CRUD]
  [AddPriorityButton / AddPriorityForm]
  [ConnectionStatus with Google Calendar OAuth]
```

### State initialization

```typescript
const [editingPriorityId, setEditingPriorityId] = useState<string | null>(null)
const [isAddingPriority, setIsAddingPriority] = useState(false)
const [awaitingOAuth, setAwaitingOAuth] = useState(false)
const [displayMode, setDisplayMode] = useState<'inline' | 'fullscreen'>('inline')

// In onAppCreated:
appRef.current = appInstance
const savedState = appInstance.getState() as WidgetState | undefined
if (savedState?.editingPriorityId) setEditingPriorityId(savedState.editingPriorityId)
if (savedState?.addFormOpen) setIsAddingPriority(true)
if (savedState?.awaitingOAuth) setAwaitingOAuth(true)
const hostCtx = appInstance.getHostContext()  // verify method name
if (hostCtx?.displayMode === 'fullscreen') setDisplayMode('fullscreen')
```

### Host context changes

```typescript
// In onAppCreated — verify callback name against installed types
appInstance.onhostcontextchanged = () => {
  const ctx = appInstance.getHostContext()
  const rawLocale = ctx?.locale ?? 'en'
  document.documentElement.lang = rawLocale.replace(/_/g, '-')
  setLocale(rawLocale)
  if (ctx?.displayMode === 'fullscreen' || ctx?.displayMode === 'inline') {
    setDisplayMode(ctx.displayMode)
  }
  setHostBottomInset(ctx?.safeArea?.bottom ?? 0)
  handleToolOutputUpdate()
}
```

### All CRUD handlers

Copy verbatim from ChatGPT `App.tsx`. Replace:
- `window.openai.callTool(name, args)` → `appRef.current?.callServerTool({ name, arguments: args })`
- `extractStructuredContent(result)` → `result?.structuredContent as { data?: ToolOutputData }`

Include all handlers:
- Priority: `handleAddPriority`, `handleUpdatePriority`, `handleDeletePriority`, `handleKeywordChange`
- Deliverable: `handleAddDeliverable`, `handleToggleDeliverable`, `handleRenameDeliverable`, `handleDeleteDeliverable`
- Goal: `handleAddGoal`, `handleToggleGoal`, `handleRenameGoal`, `handleDeleteGoal`
- Data: `refreshData`, `backfillTimeAllocation`
- Display: `handleExpandToFullscreen`, `handleMinimizeToInline`, `handleOpenAddForm`

### `isInline` prop flow

`App.tsx` → `PriorityCardWrapper` → `DeadlineCard`/`FlexibleCard` → child components.

When `isInline=true`: no edit/delete/add buttons, no CRUD handlers, sections default-collapsed, `KeywordPicker` not rendered.

### Preserved patterns from ChatGPT

- **`hasCrudDataRef` guard** — blocks stale `ontoolresult` from overwriting CRUD results. Copy exactly.
- **`backfillTimeAllocation`** — silently calls `get_priorities` after CRUD responses that lack `timeAllocation`. Use `appRef.current?.callServerTool`.
- **`lastToolOutputRef`** — prevents duplicate processing of same tool output reference.
- **State persistence** — `appRef.current?.setState(state)` replaces `window.openai.setWidgetState(state)`.

### PieChart view

Render `PieChart` when `isPieChartData(data) && data.slices.length > 0`. Display-only for this increment. No semantic grouping interaction until `allEvents` placement decision is made.

---

## `types.ts` updates

Add from ChatGPT `types.ts`:
- `PieChartData` interface
- `PieSlice` interface
- `isPieChartData` type guard
- `WidgetState` interface

Remove the `window.openai` global declaration block — not needed in Claude widget.

---

## `utils.ts` updates

Add Claude-specific helper:
```typescript
export function extractClaudeStructuredContent<T>(result: unknown): T | undefined {
  if (!result || typeof result !== 'object') return undefined
  const r = result as Record<string, unknown>
  if (r.structuredContent !== undefined) return r.structuredContent as T
  return undefined
}
```

---

## CSS

Keep `useHostStyles(app)` — injects host CSS variables. Do not hardcode colors. The host controls theming.

Call `notifyIntrinsicHeight()` (verified method name) after every state change that affects height in inline mode.

---

## What NOT to Touch

- Any file in `mcp_server/priority_guardian/` — ChatGPT widget, shared tools
- Any file in `mcp_server/priority_guardian_claude/handlers/`
- `response_adapter_dupl.py`
- Backend

---

## Build

```
cd mcp_server/priority_guardian_claude/widget-react
npm run build
```

Verify `mcp_server/priority_guardian_claude/widgets/pg-dashboard-claude.html` is updated.

---

## Manual Verification Checklist (MCP Inspector)

### Inline card compliance
- [ ] Inline card height ≤500px
- [ ] Inline card has at most 2 actions: ExpandButton always present, CalendarConnectionMinimal only if connection action is needed
- [ ] No dropdowns or popovers in inline
- [ ] No nested scrolling in inline
- [ ] Expand button opens fullscreen

### Fullscreen CRUD
- [ ] Edit priority name — saves
- [ ] Delete priority — confirmation shown, removes from list
- [ ] Add priority (deadline) — appears in list
- [ ] Add priority (flexible) — appears in list
- [ ] Add deliverable — appears in card
- [ ] Toggle deliverable done — updates
- [ ] Rename deliverable — saves
- [ ] Delete deliverable — removes
- [ ] Add goal — appears in flexible card
- [ ] Toggle goal achieved — updates
- [ ] Rename goal — saves
- [ ] Delete goal — removes
- [ ] KeywordPicker — updates card color
- [ ] Delete confirmation shown before delete

### Data and state
- [ ] TimeAllocationBar renders when Google Calendar connected
- [ ] PieChart renders when tool result is PieChartData
- [ ] Edit state survives widget remount
- [ ] `backfillTimeAllocation` fires after add_priority — progress bar restores
- [ ] Refresh button in fullscreen updates data

### Layout
- [ ] Minimize button in fullscreen returns to inline
- [ ] CalendarConnectionMinimal in inline
- [ ] ConnectionStatus in fullscreen
- [ ] `notifyIntrinsicHeight` called after height changes

---

## Definition of Done

### Widget implementation
- [ ] All 9 missing components added
- [ ] All existing components updated with CRUD props + `isInline` prop
- [ ] `App.tsx` full CRUD handler suite
- [ ] Inline: read-only, max 2 actions, no popovers, `notifyIntrinsicHeight` called
- [ ] Fullscreen: full CRUD, `FullscreenHeader`, `ConnectionStatus`, `AddPriorityForm`
- [ ] All bridge calls verified against installed TypeScript types before implementation
- [ ] No guessed `app.*` method names — every call confirmed in types
- [ ] `app` stored in ref (`appRef.current`)
- [ ] State persistence via `app.setState` / `app.getState`
- [ ] `app.onhostcontextchanged` replaces `openai:set_globals`
- [ ] PieChart view included (display only — no semantic grouping interaction)
- [ ] `hasCrudDataRef` guard preserved
- [ ] `backfillTimeAllocation` preserved
- [ ] `types.ts` includes `PieChartData`, `PieSlice`, `isPieChartData`, `WidgetState`
- [ ] Widget builds without TypeScript errors
- [ ] `pg-dashboard-claude.html` updated
- [ ] Manual verification checklist passed in MCP Inspector

### Submission blockers (verify only — do not touch shared code)
- [ ] All tools have `title` annotation — fixed in Shared-Annotations-01, verify not regressed
- [ ] All write tools have `destructiveHint: true` — fixed in Shared-Annotations-01, verify not regressed
- [ ] All read tools have `readOnlyHint: true` — verify not regressed
- [ ] Documentation page published at stable HTTPS URL with minimum 3 usage examples
- [ ] `/.well-known/oauth-protected-resource` `resource` field matches submission URL
- [ ] Screenshots ready: 3–5 PNGs, ≥1000px wide, cropped to app response, paired with prompt text (blocked until widget rendering confirmed in claude.ai)
