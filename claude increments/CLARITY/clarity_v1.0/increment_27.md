Claude Code Briefing: Increment 27 — Accessibility & Submission Readiness
Context
Clarity is in final hardening phase before OpenAI SDK app submission. Core functionality complete. Tool annotations compliant. Remaining gaps: widget accessibility and submission documentation.
Objective
Close all MUST requirements for OpenAI app submission by addressing keyboard accessibility, ARIA labeling, modal focus management, and submission documentation.

Technical Requirements
1. Semantic HTML Structure (ClusterCard, SubclusterCard, ThoughtItem)
Replace div-heavy structure with semantic elements for screen reader navigation:

Cluster title → <h3>
Subcluster title → <h4>
Thought items → <ul><li>...</li></ul>
Only ClusterCard root gets tabIndex={0} (one tab stop per cluster)
Add data-testid="cluster-card" to ClusterCard root for testing
Do NOT add tabIndex to SubclusterCard or ThoughtItem

Rationale: Screen readers navigate by headings and lists natively. Avoid tab-stop explosion (5 clusters × 3 subclusters × 5 items = 75 tab stops is unusable).
Files: ClusterCard.tsx, SubclusterCard.tsx, ThoughtItem.tsx
2. Focus Ring Styling
BLOCKING PRE-STEP: Before implementing focus rings:

Open node_modules/@openai/apps-sdk-ui/css or inspect existing SDK components in browser devtools
Find what token/class is used for primary color focus states
If outline-primary doesn't exist, use the pattern already in codebase

Do NOT guess token names. Verify they exist.
Use focus-visible: (not focus:) so mouse users don't see rings:
tsxclassName={`... focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]`}
Adjust token syntax based on verification step above.
3. SaveModal Focus Trap
Install focus-trap-react:
bashnpm install focus-trap-react
Preserve existing ARIA semantics (already present in SaveModal.tsx):

role="dialog" ✓
aria-modal="true" ✓
aria-labelledby="save-modal-title" ✓

Wrap modal content with FocusTrap and configure explicitly:
tsximport FocusTrap from 'focus-trap-react'

<FocusTrap
  focusTrapOptions={{
    clickOutsideDeactivates: true,  // Backdrop click closes modal
    escapeDeactivates: true,         // Escape closes modal
    onDeactivate: handleClose,       // Ensure focus restoration runs
  }}
>
  <div className="modal-content" role="dialog" aria-modal="true" aria-labelledby="save-modal-title">
    {/* existing modal contents */}
  </div>
</FocusTrap>
Focus management requirements:

On open: Focus moves to first focusable element (Cancel button)
Pressing Escape closes modal
Tab/Shift+Tab cycles within modal only
On close (any method): Return focus to Header's Save button

Implementation:

Pass a ref from App.tsx to Header for the Save button
Store this ref before opening modal
On modal close, restore focus to stored ref

4. Icon Accessibility Audit
Scan all components for icon-only elements:

Header.tsx: Check icon — verify aria-hidden="true" (decorative, adjacent to "Saved" text)
If any icon-only buttons exist (close, delete, etc.) → add aria-label

TagPill: No change needed. Badge renders visible text; screen readers already read it.

Non-Code Deliverables
1. Annotation Justifications Document
Create docs/ANNOTATION_JUSTIFICATIONS.md:
markdown# Tool Annotation Justifications

This document provides justification for each tool's annotations as required for OpenAI SDK app submission.

| Tool | readOnlyHint | destructiveHint | openWorldHint | Justification |
|------|--------------|-----------------|---------------|---------------|
| organize_thoughts | false | false | false | Creates ephemeral in-memory board state. No persistent storage until user explicitly calls save_board. |
| load_saved_board | true | false | false | Read-only retrieval of persisted data. No mutations to stored state. |
| read_saved_board | true | false | false | Read-only data fetch for LLM merge operations. No mutations. |
| save_board | false | true | false | Overwrites user's previously saved board. Destructive to prior persisted state. |
| prioritize_clusters | false | false | false | Modifies ephemeral priority assignments in working board. Not destructive — changes are reversible and not persisted until explicit save. |
| edit_board | false | true | false | Contains delete operations (clusters, subclusters, thought items). Destructive to working board state. |
| delete_my_data | false | true | false | Permanently deletes all user data from database. Irreversible. |

## Notes

- **readOnlyHint**: Set to `true` only for tools that have zero side effects and are safe to retry.
- **destructiveHint**: Set to `true` for any tool that overwrites or deletes user data.
- **openWorldHint**: Set to `false` for all tools — Clarity only interacts with its own backend, not external systems.
2. Submission Checklist
Create docs/SUBMISSION_CHECKLIST.md:
markdown# Clarity — OpenAI SDK App Submission Checklist

## Pre-Submission Verification

- [ ] Privacy policy live at https://www.priority-guard.com/privacy
- [ ] Support email configured in OpenAI developer portal
- [ ] Reviewer testing guide attached (docs/REVIEWER_TESTING_GUIDE.md)
- [ ] Screenshots captured showing real functionality
- [ ] Annotation justifications document attached (docs/ANNOTATION_JUSTIFICATIONS.md)

## Technical Verification

- [ ] All tools have correct annotations (readOnlyHint, destructiveHint, openWorldHint)
- [ ] Widget renders in both light and dark mode
- [ ] Keyboard navigation works (tab through clusters)
- [ ] Focus rings visible in both themes
- [ ] Modal focus trap working (Tab cycles, Escape closes)
- [ ] Screen reader navigation works (headings, lists)

## Store Listing Metadata

- [ ] App name: Clarity
- [ ] Description: Clear and accurate
- [ ] Support email: support@priority-guard.com
- [ ] Privacy policy URL: https://www.priority-guard.com/privacy
3. Reviewer Testing Guide
Create docs/REVIEWER_TESTING_GUIDE.md:
markdown# Clarity — Reviewer Testing Guide

## Installation

1. Add Clarity app from directory
2. No separate login required. Reviewer installs the app and can use tools immediately.

## Test Flow

### 1. Create Board
Type in chat:
> "I have a lot on my mind: finish report, call dentist, plan vacation, buy groceries, exercise more"

**Expected**: Widget renders with thoughts grouped into clusters.

### 2. Prioritize
Type in chat:
> "Make 'finish report' my P1"

**Expected**: P1 badge appears on the relevant cluster/item.

### 3. Save Board
Type in chat:
> "Save my board"

**Expected**: Transient "Saved" confirmation appears in widget header.

### 4. Load Saved Board (New Conversation)
Start a new conversation. Type:
> "Show my saved board"

**Expected**: Previously saved board loads with all clusters and priorities intact.

### 5. Edit Board
Type in chat:
> "Add 'send invoice' to Work cluster"

**Expected**: New thought item appears in the specified cluster.

### 6. Delete Data
Type in chat:
> "Delete all my Clarity data"

Then confirm when prompted.

**Expected**: All data deleted. Confirmation message displayed.

## Keyboard Navigation

1. Press Tab to move through clusters
2. Each cluster card should receive visible focus ring
3. Focus should not get stuck

## Modal Behavior

1. Click Save button in widget header
2. Modal opens, focus on Cancel button
3. Tab cycles between Cancel and Save only
4. Press Escape — modal closes, focus returns to Save button
4. Manual QA Script
Create docs/QA_ACCESSIBILITY.md:
markdown# Accessibility QA Checklist

Run through this checklist before submission.

## Keyboard Navigation

- [ ] Tab through widget — verify focus ring visible on each ClusterCard
- [ ] Count tab stops — should equal number of clusters (NOT subclusters or items)
- [ ] Verify focus never gets "stuck"
- [ ] Shift+Tab moves backwards correctly

## Screen Reader (VoiceOver on Mac / NVDA on Windows)

- [ ] Navigate by headings (Ctrl+Alt+H on NVDA, VO+Cmd+H on Mac)
  - Cluster names announced as h3
  - Subcluster names announced as h4
- [ ] Navigate lists
  - Thought items announced as list items
- [ ] Tags announced with visible text (no duplicate announcements)
- [ ] Priority badges announced

## Modal Focus Management

- [ ] Click Save button → modal opens
- [ ] Focus automatically on Cancel button
- [ ] Tab → focus moves to Save button
- [ ] Tab → focus returns to Cancel button (trapped)
- [ ] Shift+Tab cycles backwards
- [ ] Tab does NOT escape modal to background content
- [ ] Press Escape → modal closes
- [ ] After close → focus returns to Header Save button
- [ ] Click backdrop → modal closes
- [ ] After backdrop close → focus returns to Header Save button

## Theme Compatibility

- [ ] Toggle to dark mode
- [ ] Focus rings visible in dark mode
- [ ] All text readable in dark mode
- [ ] Toggle back to light mode
- [ ] Focus rings visible in light mode

Unit Tests
Add widget-react/src/test/Accessibility.test.tsx:
tsximport { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import App from '../App'

describe('Accessibility', () => {
  it('tab stops equal cluster count only', async () => {
    // Setup: render with mock data containing 3 clusters
    render(<App />)
    const user = userEvent.setup()

    const clusterCards = screen.getAllByTestId('cluster-card')
    expect(clusterCards).toHaveLength(3)

    await user.tab()
    expect(clusterCards[0]).toHaveFocus()

    await user.tab()
    expect(clusterCards[1]).toHaveFocus()

    await user.tab()
    expect(clusterCards[2]).toHaveFocus()

    await user.tab()
    // Focus should have left the clusters
    expect(clusterCards.some(c => c === document.activeElement)).toBe(false)
  })

  it('modal traps focus', async () => {
    render(<App />)
    const user = userEvent.setup()

    // Open modal
    const saveButton = screen.getByRole('button', { name: /save/i })
    await user.click(saveButton)

    // Modal should be open
    const modal = screen.getByRole('dialog')
    expect(modal).toBeInTheDocument()

    // Focus should be inside modal
    expect(modal.contains(document.activeElement)).toBe(true)

    // Tab several times — focus should stay inside
    await user.tab()
    expect(modal.contains(document.activeElement)).toBe(true)
    await user.tab()
    expect(modal.contains(document.activeElement)).toBe(true)
    await user.tab()
    expect(modal.contains(document.activeElement)).toBe(true)
  })

  it('modal closes on Escape and restores focus', async () => {
    render(<App />)
    const user = userEvent.setup()

    const saveButton = screen.getByRole('button', { name: /save/i })
    await user.click(saveButton)

    // Modal open
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Press Escape
    await user.keyboard('{Escape}')

    // Modal closed
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    // Focus restored to trigger
    expect(saveButton).toHaveFocus()
  })
})
```

Note: These tests require mock data setup. Adjust based on existing test infrastructure. Keep assertions minimal — test behavior, not implementation details.

---

### Integration Tests

None required. Accessibility is client-side only. Use manual QA script (`docs/QA_ACCESSIBILITY.md`).

---

### Verification Criteria

Before marking increment complete:

1. **Tab order**: Tab through widget — one stop per ClusterCard only
2. **Focus rings**: Visible in both light and dark mode
3. **Screen reader**: Headings (h3/h4) and lists (ul/li) navigate correctly
4. **Modal focus trap**: Tab cycles within modal only
5. **Modal Escape**: Pressing Escape closes modal
6. **Focus restoration**: After modal close, focus returns to Save button
7. **All unit tests pass**
8. **QA checklist completed** (`docs/QA_ACCESSIBILITY.md`)

---

### Files to Modify
```
mcp_server/clarity/widget-react/
├── package.json                    # Add focus-trap-react dependency
├── src/
│   ├── components/
│   │   ├── ClusterCard.tsx         # Semantic HTML (h3), tabIndex={0}, data-testid, focus ring
│   │   ├── SubclusterCard.tsx      # Semantic HTML (h4, ul/li), NO tabIndex
│   │   ├── ThoughtItem.tsx         # Convert to <li>, NO tabIndex
│   │   ├── Header.tsx              # Add ref to Save button for focus restoration
│   │   └── SaveModal.tsx           # Wrap with FocusTrap, Escape handling, focus restore
│   ├── App.tsx                     # Manage trigger ref, pass to Header/SaveModal
│   └── test/
│       └── Accessibility.test.tsx  # New file

docs/
├── ANNOTATION_JUSTIFICATIONS.md    # New
├── SUBMISSION_CHECKLIST.md         # New
├── REVIEWER_TESTING_GUIDE.md       # New
└── QA_ACCESSIBILITY.md             # New

Dependencies
bashnpm install focus-trap-react

Out of Scope

WCAG certification claims
Complex ARIA live regions
Skip links (widget is small, not needed)
Automated accessibility CI (use manual QA for submission)