# PG Widget — UI Polish Increment

**Scope:** Visual and interaction refinements to the Priority Guardian dashboard widget.
**Context:** Widget B (CRUD) is functionally complete. This increment addresses UI quality, visual consistency, and interaction model alignment.

---

## Pre-Requisites

Read before starting:

- `/mnt/project/openai-sdk-ui-tokens-reference.md` — Canonical design token reference. All styling MUST use these tokens.
- `/mnt/project/pg-widget-spec-v1.md` — Widget specification
- `mcp_server/priority_guardian/widget-react/src/` — Current widget source

---

## 1. Keyword Badge Shape

**Current:** Rectangular badges with sharp corners (`px-2 py-0.5 rounded`)
**Required:** Circular badges

The P1/P2/P3 keyword badges must be circles, not rectangles. Use a fixed-size circle with centered text.

Applies to: `DeadlineCard`, `FlexibleCard`, `constants.ts`

The `BADGE_COLORS` in `constants.ts` currently use custom hex colors (`bg-[#5B8DEF]`, etc.). Replace with OpenAI SDK semantic tokens:

| Keyword | Badge color | Token mapping |
|---------|-----------|---------------|
| P1 | Blue | `bg-info-soft` / `text-info` |
| P2 | Purple | `discovery` semantic token (via Badge component or equivalent) |
| P3 | Teal/Green | `bg-success-soft-alpha` / `text-success` |

Use `rounded-full` and equal `w-` / `h-` values to achieve circle shape.

---

## 2. Type Tags (Flexible / Deadline-driven)

**Current:** Plain text with emoji prefix (`⏱ Deadline`, `↻ Flexible`)
**Required:** Oval pill tags with semantic color

Use the SDK `Badge` component:

```tsx
import { Badge } from '@openai/apps-sdk-ui/components/Badge'

// Deadline type
<Badge color="warning" variant="soft" size="sm">Deadline-driven</Badge>

// Flexible type
<Badge color="info" variant="soft" size="sm">Flexible</Badge>
```

Label must be `"Deadline-driven"` (not `"Deadline"`) and `"Flexible"`.

Remove the emoji prefixes (⏱, ↻).

---

## 3. Calendar Keyword Info — Text & Position

**Current text:** `📅 Tag calendar events with **P1** to track time`
**Current position:** Middle of card, in a `bg-surface-secondary` box

**Required text:** `Use P1 in the calendar event title to track time`
**Required position:** Directly below the priority name (and below the type tag). Render as subtle secondary text, not in a highlighted box.

Remove the 📅 emoji. Remove the `bg-surface-secondary rounded-lg` container. Render as a plain `text-xs text-tertiary` line.

Applies to: `DeadlineCard`, `FlexibleCard`

---

## 4. Edit Field Styling

**Current:** Sharp-cornered inputs (`rounded` = 4px border-radius, `border border-default`)
**Required:** Modern rounded inputs matching the AddPriorityForm pattern

All edit-mode inputs and textareas in `DeadlineCard` and `FlexibleCard` must use:
- `rounded-xl` (12px border-radius)
- `focus:ring-2 focus:ring-info` (not `ring-1`)
- `px-3 py-2` padding (not `px-2 py-0.5` or `px-2 py-1`)

The AddPriorityForm already uses `rounded-md px-3 py-2 focus:ring-2 focus:ring-info`. Align all edit inputs to at least `rounded-lg`. Consistency across all forms is the requirement.

Also applies to: `DeliverableItem` inline edit input, `AddDeliverableInput` input field.

---

## 5. Disconnect Button Color

**Current:** `<Button color="secondary" variant="outline">` (gray)
**Required:** Black button

In `ConnectionStatus.tsx`, the Disconnect button should use `color="primary" variant="outline"` which renders as black outline in the OpenAI SDK token system (`--color-text` = gray-1000 = near-black in light mode, near-white in dark mode). This ensures theme-safe contrast.

Only the Disconnect button changes. Connect and Check Status buttons stay as-is.

---

## 6. E2E Deliverables — Rename & Visual Prominence

**Current label:** `Deliverables`
**Required label:** `E2E Deliverables`

Update the section header in both `DeadlineCard` and `FlexibleCard`.

Additionally, increase visual prominence:
- Section header: Change from `text-xs font-medium text-tertiary uppercase tracking-wide` to `text-sm font-semibold text-default`
- Remove `uppercase tracking-wide` — it's too quiet
- Add subtle top border already exists (`border-t border-subtle pt-3`) — keep this
- The deliverable items themselves stay as-is

---

## 7. Consistent Autosave Everywhere

**Current behavior (inconsistent):**
- `DeadlineCard`: Auto-saves priority fields on blur. Correct pattern.
- `FlexibleCard`: Has explicit Save/Cancel buttons. Does NOT auto-save.
- `DeliverableItem`: Toggle (checkbox) auto-saves immediately. Rename auto-saves on blur. Correct pattern.
- `AddDeliverableInput`: Has Add/Cancel buttons and a text input that opens on click.

**Required behavior — autosave on blur, consistently, everywhere:**
- `FlexibleCard`: Remove Save/Cancel buttons. Auto-save each field on blur, matching `DeadlineCard`'s `autoSave()` pattern. Each field saves independently.
- `DeadlineCard`: Keep current auto-save on blur. No changes to save model.
- `DeliverableItem`: Keep current behavior (toggle saves immediately, rename saves on blur). No changes.
- `AddDeliverableInput`: Keep current Add/Cancel pattern — this is a creation flow, not an edit, so explicit confirmation is correct here.

**Error feedback improvement (both cards):**
- Remove the `saveStatus` state and the "Saving..." / "Saved" inline text indicators. They add visual noise for sub-second operations.
- Only surface errors: if a save fails, show the error message from the tool (not generic "Failed to save"). Clear after 3s.
- Do NOT show any indicator for successful saves — silence means success.

---

## 8. Delete Confirmation — Modal Popup

**Current:** Replaces the card content with an inline confirmation banner (`DeleteConfirmation` component rendered instead of the card).
**Required:** Overlay/modal popup that appears ON TOP of the card, not replacing it.

Update `DeleteConfirmation.tsx` to render as a centered modal overlay (using `position: fixed` or a portal).

**Delete confirmation message format:**

For priorities:
```
Delete P1: Build my business so that it achieves breakeven?
This will also delete all deliverables. This cannot be undone.
```

The format is: `Delete {keyword}: {priority name}?` — include the keyword prefix.

The component currently receives `itemName` and `itemType`. It also needs `calendarKeyword` (for priorities) to construct this message. Update the interface.

For deliverables: Keep the existing inline confirmation pattern (the small "Remove X? Yes/No" row in `DeliverableItem`). Only priority deletion gets the modal treatment.

Modal styling:
- Semi-transparent backdrop (`bg-black/50` or equivalent)
- Centered white card with `rounded-2xl`, `shadow-xl`, `p-6`
- `bg-surface` for the modal card
- Buttons: `Delete` (`color="danger" variant="solid"`) and `Cancel` (`color="secondary" variant="ghost"`)

Modal accessibility:
- When modal opens, auto-focus the Cancel button (safe default — prevents accidental deletion)
- ESC key closes the modal (same as Cancel)
- Click on backdrop closes the modal

---

## Files to Modify

| File | Changes |
|------|---------|
| `constants.ts` | Badge colors → SDK tokens, circle dimensions |
| `DeadlineCard.tsx` | Badge circle, type tag (Badge component), calendar info text+position, edit field styling, remove saveStatus/Saving.../Saved indicators, delete modal call |
| `FlexibleCard.tsx` | Badge circle, type tag (Badge component), calendar info text+position, edit field styling, deliverables label rename, remove Save/Cancel buttons, add auto-save on blur (match DeadlineCard pattern), delete modal call |
| `DeleteConfirmation.tsx` | Refactor to modal overlay, accept `calendarKeyword` prop, update message format |
| `ConnectionStatus.tsx` | Disconnect button color |
| `DeliverableItem.tsx` | Edit input styling (rounded-lg, padding) |
| `AddDeliverableInput.tsx` | Input styling consistency |
| `App.tsx` | Pass `calendarKeyword` to delete flow if needed |

---

## Acceptance Criteria

1. P1/P2/P3 badges render as circles with SDK semantic colors
2. Type indicator shows as colored oval pill using SDK `Badge` component — "Deadline-driven" or "Flexible"
3. Calendar keyword info reads "Use P1 in the calendar event title to track time" and sits directly below the priority name
4. All edit-mode inputs use consistent modern rounded styling (minimum `rounded-lg`, `px-3 py-2`, `focus:ring-2`)
5. Disconnect button renders in black/dark color
6. Section header reads "E2E Deliverables" with increased visual weight
7. Both card types auto-save on blur — FlexibleCard refactored to match DeadlineCard pattern, Save/Cancel buttons removed
8. Deliverable toggles persist immediately, renames persist on blur (existing behavior preserved)
9. No "Saving..." / "Saved" indicators — only errors surface, and clear after 3s
10. Priority delete shows a centered modal overlay with backdrop, message includes keyword prefix
11. Delete modal: Cancel auto-focused on open, ESC closes, backdrop click closes
12. All styling uses OpenAI SDK design tokens — no custom hex colors except where SDK has no token
13. Dark mode compatibility maintained (test with `data-theme="dark"`)

---

## Unit Tests

Test the following in isolation (mock `window.openai.callTool`):

- **Autosave on blur (FlexibleCard):** Edit priority name, blur input → verify `callTool('update_priority')` called with correct field. Repeat for each flexible field (weekly_hour_target, checkpoint_date, desired_result).
- **Autosave no-op:** Edit name to same value, blur → verify `callTool` NOT called
- **Autosave error:** Mock `callTool` to reject → verify error message displayed, field reverts to original value, error clears after timeout
- **No success indicator:** Successful autosave → verify NO "Saving..." or "Saved" text rendered
- **Delete modal:** Click delete → verify modal overlay renders with correct keyword + name text
- **Delete modal cancel:** Click Cancel on modal → verify modal closes, card unchanged
- **Delete modal ESC:** Press ESC while modal open → verify modal closes
- **Delete modal focus:** Open modal → verify Cancel button has focus
- **Badge rendering:** Verify P1/P2/P3 render as circles with correct SDK color classes

---

## Integration Tests

- Full edit flow: Edit priority name (blur) → toggle deliverable → verify two separate `callTool` invocations, each persists independently
- Delete flow: Click delete → confirm in modal → verify card removed from widget
- Dark mode: Load widget with `data-theme="dark"` → verify all elements visible and correctly themed
