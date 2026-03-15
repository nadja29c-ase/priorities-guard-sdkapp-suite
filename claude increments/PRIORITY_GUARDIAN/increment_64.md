Increment Briefing — Keyword Change: Tracking Consequence Education (final)
Context
When a user changes a priority's badge (P1/P2/P3) mid-week, the weekly snapshot created at week's end uses the new keyword to scan all 7 days retroactively — including days before the change. Hours from before the swap may be misattributed. The user currently gets no warning.
The fix is purely a widget UX change: a confirmation dialog before the keyword change fires, with plain-language education about the tracking consequence and a recommendation to change on Monday. No backend changes, no new endpoints, no schema changes.

What to build
KeywordPicker.tsx: intercept the tap before calling onKeywordChange. Instead of firing immediately, set a pending keyword state and show a confirmation dialog.
Guard before opening dialog: if pendingKeyword === currentKeyword, do nothing and return immediately. This must be the first check — before any state is set.
The dialog explains:

The badge matches calendar event titles — events tagged with the new badge will start counting from now
Hours already tracked this week under the old badge may no longer count for this priority if the badge is changed now
Best time to change is Monday morning, before any events are created for the week
From Monday: tag calendar events with the new badge to start tracking toward this priority

Swap case: if the selected badge is already held by another priority, the badges will swap (this is handled by the existing backend). The dialog explains the change from currentKeyword → pendingKeyword only — do not attempt to explain both sides of the swap. The existing tooltip ("Will swap with {name}") on the badge button already communicates this.
Two actions: "Change now" (proceeds) and "Keep current badge" (dismisses, no change). The dialog informs — it does not block.

Strings — i18n.ts (EN + DE)
Add to both en and de objects. Do not remove or rename any existing keys.
keywordChangeTitle     "Change badge?"
                       "Badge ändern?"

keywordChangeBody      "Hours are counted by scanning your calendar events for the badge label.
                        Changing mid-week means hours already tracked this week under {oldKeyword}
                        may no longer count for this priority — the snapshot at week's end will
                        only see {newKeyword} events."

                       "Stunden werden erfasst, indem Kalendertermine nach dem Badge-Label
                        durchsucht werden. Ein Wechsel mitten in der Woche bedeutet, dass bereits
                        erfasste Stunden unter {oldKeyword} möglicherweise nicht mehr für diese
                        Priorität zählen — der wöchentliche Snapshot sieht nur noch
                        {newKeyword}-Termine."

keywordChangeBestTime  "Best time to change: Monday morning, before any events for the week."
                       "Bester Zeitpunkt: Montag früh, bevor Termine für die Woche erstellt wurden."

keywordChangeHowTo     "From Monday, tag your calendar events with {keyword} to track time toward
                        this priority."
                       "Ab Montag kannst du Kalendertermine mit {keyword} markieren, um Zeit für
                        diese Priorität zu erfassen."

keywordChangeConfirm   "Change now"
                       "Jetzt ändern"

keywordChangeCancel    "Keep current badge"
                       "Badge beibehalten"
{oldKeyword}, {newKeyword}, and {keyword} are interpolated by the caller before rendering — same pattern as existing {name} and {n} substitutions in the codebase.

Component changes — KeywordPicker.tsx

Add state: pendingKeyword: CalendarKeyword | null
In handleClick: first check if (kw === currentKeyword) return — then set pendingKeyword and return. Do not call onKeywordChange here.
Render the confirmation dialog when pendingKeyword !== null
Dialog content — three distinct text blocks:

Body paragraph — interpolate {oldKeyword} = currentKeyword, {newKeyword} = pendingKeyword — style text-sm text-secondary
Best-time line — style text-sm text-secondary
How-to line — interpolate {keyword} = pendingKeyword — style text-sm text-default (actionable, slightly more prominent)


"Change now": dismiss dialog (pendingKeyword = null) immediately, then call onKeywordChange(pendingKeyword)
"Keep current badge": set pendingKeyword = null only — no change fires
Swap hint tooltip ("Will swap with {name}") stays as-is on the badge buttons — no changes there

Button colors: "Change now" → color="primary" variant="solid". "Keep current badge" → color="secondary" variant="ghost". Not danger colors — this is informational, not destructive.
No loading state on dialog buttons. Dismiss immediately on confirm. The existing loadingKeyword state already handles the loading indicator on the badge buttons after the dialog closes.

Design
Read DeleteConfirmation.tsx before implementing — use it as the structural and visual reference. Dialog structure, backdrop, modal container, token usage, and button layout must be consistent with DeleteConfirmation. No hardcoded colours — design tokens only.

Accessibility & keyboard navigation
Replicate exactly the patterns from DeleteConfirmation.tsx and DeleteConfirmation.test.tsx. Read both files before implementing.
Focus on mount: auto-focus "Keep current badge" on open (safe default).
ESC key: closes dialog and fires cancel. Guard: do nothing if loadingKeyword !== null.
Focus trap: Tab/Shift+Tab stay within the dialog. Use the identical implementation from DeleteConfirmation — query focusable via 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', filter by offsetParent !== null, wrap on first/last. Attach to document, clean up on unmount.
Backdrop click: clicking the overlay (not the modal content) calls cancel. Guard: do nothing if loadingKeyword !== null.
ARIA: role="dialog", aria-modal="true", aria-labelledby="keyword-change-dialog-title" on the backdrop div. Title element gets id="keyword-change-dialog-title".

Tests — widget-react/src/__tests__/KeywordPicker.test.tsx
Read DeleteConfirmation.test.tsx before writing these tests. Use the same offsetParent mock pattern for focus trap tests.
Dialog trigger:

Clicking a different badge shows the dialog and does NOT call onKeywordChange
Clicking the current badge does nothing — no dialog, no call

Dialog content:

Body contains both old and new keyword labels
How-to line contains the new keyword

Confirm path:

"Change now" calls onKeywordChange with the correct pending keyword
"Change now" dismisses the dialog before onKeywordChange is called — dialog is gone, then loading state shows on badge buttons

Cancel paths:

"Keep current badge" does not call onKeywordChange and dismisses the dialog
ESC does not call onKeywordChange and dismisses the dialog
Backdrop click does not call onKeywordChange and dismisses the dialog

Focus & keyboard:

"Keep current badge" receives focus on mount
Tab on last button wraps focus to first
Shift+Tab on first button wraps focus to last


Pre-deploy
Read doc/OPERATIONS_PREDEPLOY.md. No migration. No backend deploy — widget only. Build with npm run build inside widget-react/ and verify output lands in ../widgets/pg-dashboard.html, not dist/.