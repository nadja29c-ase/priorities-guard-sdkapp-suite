# Briefing: Redesign AddPriorityForm Widget — Fix Step Sequence, Remove Keyword Picker

## Context

The `AddPriorityForm` widget component has a broken UX flow. Current step sequence: **type → keyword → fields (including name)**. This is backwards and confusing:

1. User is asked to choose deadline/flexible before naming their priority
2. User is forced to manually pick a keyword (P1/P2/P3) — meaningless to them
3. Priority name comes last, buried inside the fields step

The form should mirror the conversational onboarding flow and follow natural thinking order.

## Goal

Redesign the form step sequence to: **name → type → fields**. Remove the keyword picker step entirely — backend auto-assigns the next available keyword. The user can reassign keywords later via the existing `KeywordPicker` component in the dashboard priority cards.

## What Changes

### Widget component only — no backend or MCP tool changes

The `add_priority` private widget tool and backend `POST /api/priority-guardian/priorities` endpoint already support omitting `calendar_keyword` (auto-assigns first available). No backend changes needed.

### Changes summary

1. **`AddPriorityForm.tsx`** — new step sequence, remove keyword step, move name to first step
2. **`KeywordPicker.tsx`** — NOT deleted. Still used by `DeadlineCard.tsx` and `FlexibleCard.tsx` for post-creation keyword reassignment
3. **Rebuild widget** — `npm run build` to regenerate `pg-dashboard.html`

## New Step Sequence

```
type FormStep = 'name' | 'type' | 'fields'
```

### Step 1: `'name'`
- Heading: "Add Priority"
- Label: "What do you want to track?"
- Input: text field, max 100 chars, placeholder: "e.g., Ship v1.0, Client outreach"
- Next button: `disabled={!name.trim()}` — visually disabled when empty, no silent no-ops
- Next: proceeds to `'type'` when name is non-empty
- Cancel button

### Step 2: `'type'`
- Back button → returns to `'name'`
- Heading: "What kind of priority?"
- Two option cards (keep existing grid layout):
  - **Deadline**: "Has a hard end date" (keep existing icon + description)
  - **Flexible**: "Ongoing weekly commitment" (update description from "Ongoing weekly hours" — "hours" is premature, user hasn't set hours yet)
- Clicking a type proceeds directly to `'fields'`
- Cancel button

### Step 3: `'fields'`
- Back button → returns to `'type'`
- Heading: "Deadline Priority" or "Flexible Priority" (keep existing)
- **Name field is removed from this step** — it's now in step 1
- Type-specific fields only:
  - Deadline: deadline date picker
  - Flexible: weekly hour target, checkpoint date, initial goal
- Create Priority button + Cancel button

## State Changes

Remove:
- `selectedKeyword` state — no longer needed
- `'keyword'` from `FormStep` type

Keep:
- `priorityType` state — still needed
- All field states (`name`, `deadline`, `weeklyHourTarget`, `checkpointDate`, `initialGoalText`)

Update:
- Initial step: `useState<FormStep>('name')` (was `'type'`)

## Navigation Logic

```typescript
const handleNameNext = () => {
  if (name.trim()) {
    setError(null) // Clear stale error from previous steps
    setStep('type')
  }
}

const handleTypeSelect = (type: PriorityType) => {
  setError(null) // Clear stale error from previous steps
  setPriorityType(type)
  setStep('fields')
}

const handleBack = () => {
  if (step === 'fields') {
    setStep('type')
  } else if (step === 'type') {
    setStep('name')
  }
  setError(null)
}
```

No keyword selection logic. No `availableKeywords.length === 1` shortcut. Straight through.

## Submit Payload Change

Remove `calendar_keyword` from the submit payload. Backend auto-assigns:

```typescript
const handleSubmit = async () => {
  // ... validation ...
  const data: Parameters<typeof onAdd>[0] = {
    name: name.trim(),
    type: priorityType,
    // NO calendar_keyword — backend auto-assigns
  }
  // ... type-specific fields same as before ...
}
```

## Props Change

`availableKeywords` prop is still needed — but only to determine if the "Add Priority" button should be shown at all (when `availableKeywords.length === 0`, max priorities reached, form returns `null`). The prop is NOT used inside the form steps anymore.

## Design Requirements

Follow OpenAI SDK design tokens. The existing form already uses them (`bg-surface`, `border-default`, `text-default`, `text-secondary`, `rounded-xl`, etc.). Maintain this. Specifically:

- Step 1 name input: same styling as existing inputs in step 3 (`text-sm text-default bg-surface border border-default rounded-md px-3 py-2`)
- Use `Button` from `@openai/apps-sdk-ui/components/Button` for all buttons (already done)
- "Next" button on name step: use `color="primary" variant="solid"` — same as "Create Priority" button

## Files Modified

1. `mcp_server/priority_guardian/widget-react/src/components/AddPriorityForm.tsx` — redesign step sequence

## Files NOT Modified

- `KeywordPicker.tsx` — still used by priority cards for reassignment
- `DeadlineCard.tsx`, `FlexibleCard.tsx` — no changes
- Backend, MCP tools — no changes
- `App.tsx` — no changes (passes same props to `AddPriorityForm`)

## Post-Change

Rebuild the widget:
```bash
cd mcp_server/priority_guardian/widget-react
npm run build
```

This regenerates `mcp_server/priority_guardian/widgets/pg-dashboard.html`.

## Unit Tests

**File:** `mcp_server/priority_guardian/widget-react/src/__tests__/AddPriorityForm.test.tsx` (update existing or create)

1. **test_initial_step_is_name** — render form, assert name input is visible, type selection is not.

2. **test_name_step_next_disabled_when_empty** — render form, assert Next button has `disabled` attribute when name is empty or whitespace-only.

3. **test_name_step_advances_to_type** — enter name, click Next, assert type selection cards are visible.

4. **test_type_step_advances_to_fields** — enter name, advance to type, click "Deadline", assert deadline field is visible.

5. **test_back_from_type_returns_to_name** — advance to type step, click back, assert name input is visible with preserved value.

6. **test_back_from_fields_returns_to_type** — advance to fields step, click back, assert type selection is visible.

7. **test_submit_does_not_include_calendar_keyword** — fill full form, submit, assert `onAdd` was called with payload that does NOT contain `calendar_keyword`.

8. **test_form_hidden_when_no_available_keywords** — render with `availableKeywords=[]`, assert form returns null.

9. **test_name_preserved_across_steps** — enter name, go to type, go back, assert name input still has the entered value.

## Acceptance Criteria

- [ ] Form step sequence is: name → type → fields
- [ ] No keyword picker step exists
- [ ] `calendar_keyword` is NOT sent in submit payload
- [ ] Name input is in step 1, not step 3
- [ ] Back navigation works correctly across all steps
- [ ] Name value is preserved when navigating back
- [ ] Form still returns null when `availableKeywords` is empty (max reached)
- [ ] `KeywordPicker.tsx` is NOT deleted (used by priority cards)
- [ ] All existing widget functionality unaffected
- [ ] Widget rebuilt and `pg-dashboard.html` regenerated
- [ ] Uses OpenAI SDK design tokens consistently
- [ ] All inputs have associated `<label>` elements, all icon-only buttons have `aria-label`
- [ ] Next button on name step is `disabled` when name is empty
- [ ] Flexible type card description updated from "Ongoing weekly hours" to "Ongoing weekly commitment"
