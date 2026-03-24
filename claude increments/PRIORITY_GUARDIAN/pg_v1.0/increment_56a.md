Increment 56a — Fix iOS state overwrite on expand
Context: On iOS, performing any CRUD operation then expanding to fullscreen causes the widget to revert to stale data. Confirmed by observation: inline shows correct post-CRUD state, fullscreen shows old pre-CRUD state (different count AND different total). Root cause: updateDataFromResponse updates React state after CRUD but never advances lastToolOutputRef, so handleToolOutputUpdate sees a stale reference on expand and overwrites state.

File: mcp_server/priority_guardian/widget-react/src/App.tsx
Change 1 — Fix the ref bug.
In updateDataFromResponse, after the notifyHeight() call, add:
ts// Advance ref to prevent handleToolOutputUpdate from overwriting CRUD result on next set_globals
const currentToolOutput = window.openai?.toolOutput
if (currentToolOutput) {
  lastToolOutputRef.current = currentToolOutput
}
Change 2 — Remove all [PG:*] console.log statements. There are four:

[PG:loadData] in loadData
[PG:handleToolOutputUpdate] in handleToolOutputUpdate
[PG:updateDataFromResponse] in updateDataFromResponse
[PG:handleExpandToFullscreen] in handleExpandToFullscreen

Change 3 — Revert the diagnostic error messages in handleToggleDeliverable back to standard. Both throw new Error blocks that contain diagnostic JSON output should be replaced with:
tsthrow new Error("Couldn't save. Try again.")
Change 4 — Verify handleExpandToFullscreen matches this exactly (re-apply H4 fix if it was reverted in a prior commit):
tsconst handleExpandToFullscreen = useCallback(async () => {
  try {
    await window.openai?.requestDisplayMode?.({ mode: 'fullscreen' })
  } catch {
    // Host may not support requestDisplayMode — fall through
  }
  setDisplayMode('fullscreen')
  notifyHeight()
}, [notifyHeight])
If it already looks like this, no change needed.

No Python backend changes in this increment.
No new tests required.
Read OPERATIONS_PREDEPLOYMENT.md before committing.