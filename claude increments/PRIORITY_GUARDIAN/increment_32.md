# Widget Fix: GoalItem Edit/Delete Parity with DeliverableItem

## Problem

`GoalItem.tsx` only implements toggle (achieved/not achieved). The `onRename` and `onDelete` props are declared in the interface but **completely unused in the component body**. Users cannot edit goal text or delete individual goals from the widget.

The full stack is already wired and working:
- **Backend:** `PUT /priorities/{id}/goals/{gid}` and `DELETE /priorities/{id}/goals/{gid}` endpoints exist
- **MCP tools:** `update_goal` (accepts `text` and/or `achieved`) and `delete_goal` exist and are registered as private, widget-accessible
- **App.tsx:** `handleRenameGoal` and `handleDeleteGoal` are implemented, call the correct tools, and update state from response
- **FlexibleCard → GoalSection → GoalItem:** Props are threaded all the way down

**Only `GoalItem.tsx` is broken.** It accepts `onRename` and `onDelete` but renders neither edit nor delete UI.

## Reference Implementation

`DeliverableItem.tsx` is the canonical pattern. It provides:

1. **Double-click to edit** — text becomes an input field
2. **Hover actions** — edit (pencil) and delete (trash) icons appear on hover via `group/group-hover:opacity` pattern
3. **Inline editing** — auto-save on blur, Enter to save, Escape to cancel, revert on error
4. **Delete confirmation** — inline "Remove [name]?" with Yes/No, replaces the entire row temporarily
5. **Loading + error states** — `isLoading` disables interactions, `showError` with 3-second auto-clear timeout
6. **Keyboard accessible** — all actions reachable via keyboard, proper `aria-label` attributes

## What To Do

Update `GoalItem.tsx` to have the same CRUD interactions as `DeliverableItem.tsx`. The component currently has only toggle — it needs edit and delete.

### Field mapping (DeliverableItem → GoalItem)

| DeliverableItem | GoalItem |
|---|---|
| `deliverable.name` | `goal.text` |
| `deliverable.done` | `goal.achieved` |
| `onRename(id, name)` | `onRename(id, text)` |
| `onDelete(id)` | `onDelete(id)` |
| `onToggle(id, done)` | `onToggle(id, achieved)` |

### Visual differences from DeliverableItem

- GoalItem uses an **18px circular checkbox** (green `bg-success-solid` when achieved) — keep this, don't change to DeliverableItem's square checkbox
- GoalItem uses `line-through text-tertiary` on achieved text — keep this
- Hover edit/delete icons should use the same SVG paths and `group-hover:opacity` pattern as DeliverableItem
- Delete confirmation should follow the same inline pattern: `Remove "[goal text]"?` with Yes/No

### States to add (currently missing)

- `isEditing` — local boolean state
- `editText` — local string state (initialized from `goal.text`)
- `showDeleteConfirm` — local boolean state  
- `isLoading` — local boolean state (currently exists but only used for toggle)
- `error` — local string state (currently exists)

### Interactions to add (currently missing)

- Double-click on goal text → enters edit mode (input field, auto-focused, text selected)
- Hover on row → shows edit (pencil) and delete (trash) icons (use `group`/`group-hover:opacity-0`/`group-hover:opacity-100` pattern)
- Edit icon click → enters edit mode
- Blur on edit input → save if changed, cancel if unchanged or empty
- Enter key → save edit
- Escape key → cancel edit, revert text
- Delete icon click → show inline delete confirmation
- Confirm delete → call `onDelete`, show loading
- Cancel delete → hide confirmation
- Error handling → 3-second auto-clear timeout, same `showError` pattern as DeliverableItem

### What NOT to change

- GoalSection.tsx — already correctly passes `onRename` and `onDelete` to GoalItem
- FlexibleCard.tsx — already correctly passes goal handlers to GoalSection
- App.tsx — all 4 goal handlers already work
- Backend endpoints — already exist and tested
- MCP tools — already registered and working
- GoalItem's existing toggle behavior — keep working, just add edit/delete alongside it

## Acceptance Criteria

1. User can double-click goal text to enter edit mode
2. Edit saves on blur (if text changed) with auto-save pattern
3. Enter saves, Escape cancels edit
4. Edit/delete icons appear on hover (same `group-hover` pattern as DeliverableItem)
5. Delete shows inline confirmation "Remove [text]?" with Yes/No
6. Loading state disables all interactions
7. Errors auto-clear after 3 seconds
8. Empty text reverts to original (no empty goals allowed)
9. All interactive elements have proper `aria-label` attributes
10. Keyboard navigable (Tab to actions, Enter to activate)
11. Dark mode works (all colors use SDK design tokens, no hardcoded colors)
12. Widget builds successfully to single HTML file

## Unit Tests

File: Add tests to existing widget test file or create `__tests__/GoalItem.test.tsx`

Test the GoalItem component in isolation with mocked props:

1. **Renders goal text and toggle** — baseline (should already pass)
2. **Double-click enters edit mode** — simulate doubleClick on text, verify input appears
3. **Edit save on blur** — enter edit mode, change text, blur → verify `onRename` called with `(goal.id, newText)`
4. **Edit cancel on Escape** — enter edit mode, press Escape → verify text reverted, `onRename` NOT called
5. **Edit save on Enter** — enter edit mode, change text, press Enter → verify `onRename` called
6. **Empty text reverts** — enter edit mode, clear text, blur → verify text reverted to original, `onRename` NOT called
7. **Delete confirmation flow** — click delete icon → verify confirmation appears → click Yes → verify `onDelete` called
8. **Delete cancel** — click delete icon → click No → verify confirmation hidden, `onDelete` NOT called
9. **Hover shows action buttons** — verify edit/delete buttons exist in DOM (CSS hover is not testable in unit tests, just verify elements render)
10. **Loading state disables interactions** — while `onToggle` promise is pending, verify click handlers are no-ops

## Integration Tests

No integration tests needed. The backend goal CRUD endpoints and MCP tools are already tested. This is a widget-only component fix.

## Build Verification

After changes:
1. `cd mcp_server/priority_guardian/widget-react && npm run build` must succeed
2. Output `widgets/pg-dashboard.html` must be a valid single HTML file
3. Existing tests must still pass: `npm run test`
