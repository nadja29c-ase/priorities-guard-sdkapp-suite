Good. Both files confirmed. The pattern is identical in both. Here is the Claude Code brief.

Claude Code Brief — Increment: Keyboard Accessibility Fix for Priority Name <h3>
Context
DeadlineCard.tsx and FlexibleCard.tsx both render the priority name as an <h3> with an onClick handler in view (non-editing) mode. This element is interactive — it opens edit mode on click — but it is not keyboard-accessible: no tabIndex, no onKeyDown. This violates OpenAI submission requirement #10 (all interactive elements reachable via keyboard). It is a submission blocker.
The fix is surgical: two files, one element each, identical pattern.

What to change
File 1: mcp_server/priority_guardian/widget-react/src/components/DeadlineCard.tsx
Locate the <h3> in the non-editing branch of the header row. It currently looks like this:
tsx<h3
  className="text-sm font-semibold flex-1 truncate cursor-pointer hover:opacity-80 text-default"
  onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
  title="Click to edit"
>
  {priority.name}
</h3>
Replace with:
tsx<h3
  className="text-sm font-semibold flex-1 truncate cursor-pointer hover:opacity-80 text-default focus:outline-none focus-visible:ring-1 focus-visible:ring-[var(--color-border-focus,currentColor)] rounded"
  onClick={(e) => { e.stopPropagation(); onStartEdit(); }}
  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onStartEdit(); } }}
  tabIndex={0}
  role="button"
  aria-label={`${priority.name} — ${t('clickToEdit')}`}
>
  {priority.name}
</h3>
File 2: mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx
Locate the identical <h3> block. Same replacement as above — the pattern is character-for-character identical in both files.

i18n key required
Add one new key to src/i18n.ts in both locales:
ts// In messages.en:
clickToEdit: 'click to edit',

// In messages.de:
clickToEdit: 'zum Bearbeiten klicken',
Add it under the existing // Common actions section. Add clickToEdit to the TranslationKey type (it is inferred from messages via keyof typeof messages['en'] — no manual addition needed if the type is derived that way; verify before assuming).

What NOT to change

Do not touch the edit pencil button — it is already keyboard-accessible and correct.
Do not touch title="Click to edit" — keep it as a tooltip for mouse users.
Do not change any other component.
Do not refactor the edit flow or add any new state.
Do not touch the autoFocus input that appears when isEditing is true — that is separate and already correct.


Pre-deployment
Read OPERATIONS_PREDEPLOY.md before committing. This is a widget-only change — no backend migrations, no tool changes.
Build the widget (npm run build in widget-react/) and verify the compiled output is in widgets/pg-dashboard.html before deploying.

Tests
Add to the existing keyboard navigation test block in src/__tests__/ (or create DeadlineCard.test.tsx / FlexibleCard.test.tsx if none exist):
Unit tests:

Pressing Enter on the <h3> calls onStartEdit
Pressing Space on the <h3> calls onStartEdit
The <h3> has tabIndex={0}
The <h3> has role="button"
The aria-label contains the priority name

No integration tests needed — this is a pure UI interaction change with no tool calls or backend involvement. Sonnet 4.6Claude is AI and can make mistakes. Please double-check responses.