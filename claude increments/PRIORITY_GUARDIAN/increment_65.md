Increment Briefing — Fix: Progress Bar Hidden When Google Calendar Disconnected
Problem
TimeAllocationBar is visible even after Google Calendar is disconnected. The component correctly returns null when timeAllocation is undefined, but timeAllocation state in App.tsx is never cleared on disconnect.
The CRUD preservation guard in updateDataFromResponse and handleToolOutputUpdate intentionally skips clearing timeAllocation when a response omits it (to preserve calendar data across add/update/delete operations). This same guard also silently ignores the disconnect case, where the backend returns google_connected: false with timeAllocation absent — leaving the stale state in place.
What to fix — App.tsx only
Find every isDashboardData( guard in App.tsx that writes to setTimeAllocation. There are three such paths: loadData, updateDataFromResponse, handleToolOutputUpdate. Apply the same change to all of them.
Current pattern (all three paths):
tsif (isDashboardData(content.data) && content.data.timeAllocation !== undefined) {
  setTimeAllocation(content.data.timeAllocation)
}
Replace with:
tsif (isDashboardData(content.data)) {
  if (content.data.timeAllocation !== undefined) {
    setTimeAllocation(content.data.timeAllocation)
  } else if (
    content.data.timeAllocation === undefined &&
    content.data.google_connected === false
  ) {
    setTimeAllocation(undefined)
  }
}
The explicit google_connected === false condition is intentional — it prevents any CRUD response that accidentally omits google_connected from clearing the bar. The condition must be exact: both timeAllocation === undefined AND google_connected === false.
Also add a render guard in App.tsx where TimeAllocationBar is rendered. Currently:
tsx<TimeAllocationBar
  timeAllocation={timeAllocation}
  ...
/>
Replace with:
tsx{dashboardData?.google_connected && (
  <TimeAllocationBar
    timeAllocation={timeAllocation}
    ...
  />
)}
This is defence in depth — the bar cannot render if the backend says Google Calendar is disconnected, regardless of what's in state.
No other files
No backend changes. No new components. No i18n changes. No schema changes. No migration.
Tests — App.test.tsx
Read the existing test file and src/test/setup.ts before writing tests. setMockPriorities already accepts a timeAllocation fourth parameter — use it.
Add a new describe block: TimeAllocationBar visibility
Test 1 — hides bar when google_connected is false
Set up with setMockPriorities([], false, [], undefined) — no connection, no timeAllocation. Assert TimeAllocationBar is not in the document (query by 'Time allocation this week' text or the section heading).
Test 2 — shows bar when google_connected is true and timeAllocation is present
Set up with setMockPriorities([], true, [], sampleTimeAllocation) where sampleTimeAllocation is a valid TimeAllocation object. Assert the heading is visible.
Test 3 — CRUD response does not clear the bar
Initial state: google_connected: true, timeAllocation present. Mock callTool to return a CRUD-style response: { google_connected: true, priorities: [...] } with no timeAllocation. Trigger a CRUD action (e.g. toggle a deliverable checkbox). After the call resolves, assert the bar heading is still in the document.
Test 4 — disconnect clears the bar
Initial state: google_connected: true, timeAllocation present. Mock callTool to return { google_connected: false, priorities: [] } with no timeAllocation. Trigger the disconnect flow (click the Disconnect button, confirm). After the call resolves, assert the bar heading is no longer in the document.
The sampleTimeAllocation fixture can be defined locally in the test file — copy the shape from TimeAllocationBar.test.tsx.
Pre-deploy
Read doc/OPERATIONS_PREDEPLOY.md. No migration. No backend deploy. Build with npm run build inside widget-react/, verify output lands in ../widgets/pg-dashboard.html.