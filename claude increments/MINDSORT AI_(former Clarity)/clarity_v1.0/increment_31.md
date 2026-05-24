# Increment: Remove Save Confirmation Modal

**Date:** 2025-12-25  
**Component:** Clarity Widget (React)  
**Priority:** High (submission blocker - iOS modal positioning bug)

---

## Context

The save confirmation modal has a positioning bug on iOS ChatGPT app. `position: fixed` inside iframes is a known WebKit bug with no clean CSS fix. The ChatGPT SDK's `requestModal` API exists but is undocumented and risky.

**Decision:** Remove the modal entirely. One-tap save with inline warning text.

---

## Objective

Replace two-tap save flow (tap Save → modal → confirm) with one-tap save flow (tap Save → done). Add static info text so users know only 1 board can be saved.

---

## Current State

**Files involved:**
- `widget-react/src/App.tsx` — contains modal state, SaveModal import, modal trigger
- `widget-react/src/components/SaveModal.tsx` — modal component (to be deleted)

**Current flow:**
1. User taps Save button
2. `setIsModalOpen(true)` opens modal
3. Modal shows "This will overwrite..." warning
4. User taps Confirm in modal
5. `handleSave()` executes
6. Modal closes, "✓ Saved" appears

---

## Target State

**New flow:**
1. User taps Save button
2. `handleSave()` executes immediately
3. Button shows "Saving..." during operation
4. "✓ Saved" appears on success (existing behavior)
5. Button returns to "Save" after 3 seconds

**Static info text:** Always visible below Save button: "Only 1 board can be saved"

---

## Requirements

### App.tsx Changes

1. **Remove state:** `isModalOpen` state variable and setter
2. **Remove import:** `SaveModal` component import
3. **Remove JSX:** `<SaveModal ... />` component usage
4. **Modify button:** `onClick` calls `handleSave` directly (not `setIsModalOpen(true)`)
5. **Add info text:** Below the Save button, add helper text with SDK tokens:
   - Text: "Only 1 board can be saved"
   - Styling: `text-xs text-secondary mt-1`
   - Position: Inside the sticky footer div, after the Button

### Delete File

Delete `widget-react/src/components/SaveModal.tsx` entirely.

### Preserve

- `saveButtonRef` — still needed for focus management after save completes
- `handleSave` function — unchanged
- `isSaving` state — unchanged (drives "Saving..." button state)
- `showSaved` state — unchanged (drives "✓ Saved" feedback)
- `saveError` state — unchanged (drives error display)
- Transient "✓ Saved" feedback with `aria-live="polite"` — unchanged

---

## Technical Constraints

### SDK Compliance
- Use `text-secondary` token (not hardcoded gray) — responds to dark mode
- Use `text-xs` for helper text size — consistent with SDK typography

### Accessibility
- Info text is purely informational, not interactive
- No ARIA role needed (static text)
- Save button already has proper `aria-label`

### Focus Management
- After save completes, focus should remain on Save button (already handled by existing logic)
- The `setTimeout(() => saveButtonRef.current?.focus(), 0)` was originally for modal close focus restoration
- **Keep this line** — it's harmless and ensures focus returns to Save button after async operation
- **Add a code comment** explaining its purpose (e.g., `// Restore focus to Save button after async save completes`) so future refactors don't remove it incorrectly

---

## Unit Tests

**File:** `widget-react/src/__tests__/App.test.tsx` (or similar)

Test cases to add/modify:

1. **Save button triggers save directly**
   - Render App with clusters
   - Click Save button
   - Verify `window.openai.callTool` called with 'save_board'
   - No modal appears

2. **Info text is visible**
   - Render App
   - Verify text "Only 1 board can be saved" is in the document

3. **Saved feedback appears on success**
   - Mock `callTool` to return `{ saved: true }`
   - Click Save
   - Verify "Saved" text appears

4. **Button shows Saving state**
   - Mock `callTool` to delay
   - Click Save
   - Verify button is disabled during save

Test cases to remove:
- Any tests that verify modal opening
- Any tests that interact with modal confirm/cancel

---

## Integration Tests

**Scope:** Full widget render with mocked `window.openai`

1. **Happy path: Save flow**
   - Load widget with clusters from `toolOutput`
   - Click Save
   - Verify callTool invoked
   - Verify "Saved" feedback appears
   - Verify button re-enables

2. **Error handling: Save fails**
   - Mock `callTool` to throw
   - Click Save
   - Verify error message appears
   - Verify button re-enables

3. **Empty state: No clusters**
   - Load widget with empty clusters
   - Verify Save button is disabled
   - Verify info text still visible

---

## Validation Criteria

- [ ] No modal appears when Save is clicked
- [ ] Save executes immediately on button click
- [ ] "Only 1 board can be saved" text visible below Save button
- [ ] Text uses `text-secondary` token (adapts to dark mode)
- [ ] "✓ Saved" feedback still works
- [ ] "Saving..." button state still works
- [ ] Error handling still works
- [ ] SaveModal.tsx file deleted
- [ ] No TypeScript errors
- [ ] All existing tests pass (after updating modal-related tests)
- [ ] Widget renders correctly in both light and dark mode

---

## Clarifications

### Info Text Wording

Text as specified is compliant:
- **Required:** "Only 1 board can be saved"

Optional improvement (not required):
- "Only one board can be saved at a time" — reduces ambiguity but adds words

Either is acceptable. Do not block on wording choice.

---

## Optional Hardening (Not Required)

These are nice-to-haves for robustness. Do not block the increment on these:

1. **`aria-describedby` on Save button**
   - Link the button to the helper text via `aria-describedby`
   - Screen readers would announce the helper text when button is focused
   - Example: `<p id="save-hint">...</p>` + `<Button aria-describedby="save-hint">`

2. **Snapshot test for footer layout**
   - Guards against future layout regressions
   - Adds maintenance burden — optional

---

## Out of Scope

- Adding `setWidgetState` (separate increment)
- Adding `notifyIntrinsicHeight` (separate increment)
- Localization (future)
- Any backend changes

---

## Reference Files

- Current App.tsx: `mcp_server/clarity/widget-react/src/App.tsx`
- Current SaveModal.tsx: `mcp_server/clarity/widget-react/src/components/SaveModal.tsx`
- SDK tokens: `@openai/apps-sdk-ui/css` (imported in main.css)