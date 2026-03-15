Claude Code briefing — Increment [next number]: Pre-submission fixes
Read OPERATIONS_PREDEPLOYMENT.md before committing anything.
Scope: one component bug fix + test fixture updates. No backend, no MCP, no OAuth, no layout, no protocol changes.

Fix 1 — ConnectionStatus.tsx: Silent failure when connect_url is missing
File: mcp_server/priority_guardian/widget-react/src/components/ConnectionStatus.tsx
In handleConnect, if connect_google_calendar returns successfully but connectUrl is falsy, the function exits silently — no error is shown, the user sees the Connect button return to normal with no feedback.
Add an else branch to the existing if (connectUrl) block:
tsif (connectUrl) {
  if (window.openai.openExternal) {
    window.openai.openExternal({ href: connectUrl })
  } else {
    window.open(connectUrl, '_blank')
  }
  onAwaitingOAuthChange(true)
} else {
  setError(t('failedToConnect'))
}
Use t('failedToConnect') — this key already exists in i18n.ts and is already used in the catch block of this same function. Do not introduce any new i18n keys.

Fix 2 — Test fixture updates (test files only, no component changes)
Context: Priority type has goals: Goal[] as a required field (non-optional). Two test files have fixtures that predate this field, causing TypeScript compile errors that fail entire test files.
src/__tests__/App.test.tsx

Add goals: [] to the flexiblePriority fixture. Remove the desiredResult field — it no longer exists in the Priority type.
For any test case that asserts on the text 'Complete first 10 chapters' (the old desiredResult value): update the test to match current behavior. Do not delete test cases unless the feature they cover no longer exists. If the test was covering goal display, update the fixture to include a goal with that text and keep the assertion.

src/__tests__/HourRing.test.tsx — FlexibleCard + HourRing Integration describe block
The mockHandlers object is missing props that FlexibleCardProps currently requires. Add exactly these missing props:
tspriorities: [],
onKeywordChange: vi.fn().mockResolvedValue(undefined),
onAddGoal: vi.fn().mockResolvedValue(undefined),
onToggleGoal: vi.fn().mockResolvedValue(undefined),
onRenameGoal: vi.fn().mockResolvedValue(undefined),
onDeleteGoal: vi.fn().mockResolvedValue(undefined),
Also verify basePriority in this describe block has goals: [].
Do not change any component code.

Verification: Run npx vitest run from widget-react/. All tests must pass before committing. Fix 1 requires a widget rebuild and deploy. Fix 2 (test files only) does not.