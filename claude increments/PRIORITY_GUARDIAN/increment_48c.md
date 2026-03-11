Increment 48c — Fix isInitializedRef one-shot loader
Problem
loadData() in App.tsx bails immediately if isInitializedRef.current is true:
tsconst loadData = useCallback(() => {
  if (isInitializedRef.current) return  // ← one-shot guard
  ...
  isInitializedRef.current = true
}, [notifyHeight])
This guard prevents double-loads on mount, but also silently drops every subsequent openai:set_globals event after the first load. openai:set_globals is the host event that fires when new toolOutput arrives — meaning if the user triggers a second tool call in the same conversation (e.g. calls get_priorities again), the widget never updates.

What to change
File: mcp_server/priority_guardian/widget-react/src/App.tsx only.
Split loadData's two responsibilities:
1. loadData — first load only (keep as-is, plus set lastToolOutputRef)

Keeps the isInitializedRef one-shot guard — do not remove it
After successfully parsing and setting state, also set lastToolOutputRef.current = window.openai?.toolOutput
Handles the loading/error state and isInitialized flag — this logic stays exactly as it is

2. handleToolOutputUpdate — called on every subsequent openai:set_globals event

Only runs if isInitializedRef.current is true (widget already initialized)
Guard: if window.openai?.toolOutput is absent, or is the same reference as lastToolOutputRef.current, return immediately — do nothing
Otherwise: call the existing getToolOutput() from utils.ts (already used by loadData — do not duplicate this logic)
Call updateDataFromResponse with the parsed result (already exists in the component — use it)
Update lastToolOutputRef.current = window.openai?.toolOutput
notifyHeight is handled by the existing useEffect hooks that already react to state changes — do not call it directly in handleToolOutputUpdate

3. lastToolOutputRef — new ref

Add const lastToolOutputRef = useRef<unknown>(null) alongside the existing isInitializedRef
Used to detect whether toolOutput has actually changed on each openai:set_globals event

4. Update the useEffect that wires openai:set_globals:
tsuseEffect(() => {
  loadData()

  const handleSetGlobals = () => {
    if (isInitializedRef.current) {
      handleToolOutputUpdate()
    } else {
      loadData()
    }
  }

  window.addEventListener('openai:set_globals', handleSetGlobals, { passive: true })
  return () => {
    window.removeEventListener('openai:set_globals', handleSetGlobals)
  }
}, [loadData, handleToolOutputUpdate])

Constraints

isInitializedRef and the one-shot guard in loadData must not be removed
getToolOutput() from utils.ts is already the shared parsing function — use it in both loadData and handleToolOutputUpdate, do not duplicate or inline parsing logic
handleToolOutputUpdate must be wrapped in useCallback with appropriate dependencies
openai:set_globals fires for theme, displayMode, locale, and other host events — not only toolOutput changes. The lastToolOutputRef comparison is the guard that makes handleToolOutputUpdate a no-op in those cases
Do not change any CRUD handlers, display mode logic, widgetState persistence, or any other part of App.tsx


Build and verify
After the change, rebuild the widget (npm run build in widget-react/) and verify widgets/pg-dashboard.html is updated.
Normal Render deploy required. Runtime behavior change: widget now updates when new toolOutput arrives on a second tool call in the same conversation, including on iOS WKWebView.