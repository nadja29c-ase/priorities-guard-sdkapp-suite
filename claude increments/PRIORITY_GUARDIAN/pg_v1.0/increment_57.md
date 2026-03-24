Increment 57 — Display Mode Fix
Scope: App.tsx only. No backend, no migration, no other component.

Change 1 — Fix desktop regression on expand
Current code:
tsconst handleExpandToFullscreen = useCallback(async () => {
  try {
    await window.openai?.requestDisplayMode?.({ mode: 'fullscreen' })
  } catch { }
  setDisplayMode('fullscreen')
  notifyHeight()
}, [notifyHeight])
Problem: await requestDisplayMode called unconditionally. Desktop now responds with a full panel takeover. The await changes timing — host may emit openai:set_globals during the await, potentially overwriting React state before setDisplayMode runs.
Fix:
tsconst handleExpandToFullscreen = useCallback(() => {
  try {
    if (
      window.openai?.requestDisplayMode &&
      (window.openai as OpenAIHost).displayMode !== 'fullscreen'
    ) {
      window.openai.requestDisplayMode({ mode: 'fullscreen' })
    }
  } catch { }
  setDisplayMode('fullscreen')
  notifyHeight()
}, [notifyHeight])
No async, no await. Fire-and-forget. setDisplayMode is the optimistic update and runs unconditionally.

Change 2 — Fix Minimize not working on iOS
Current code:
tsconst handleMinimizeToInline = useCallback(() => {
  setDisplayMode('inline')
  notifyHeight()
}, [notifyHeight])
Problem: Never tells the host to exit fullscreen. iOS host stays fullscreen — user trapped.
Fix:
tsconst handleMinimizeToInline = useCallback(() => {
  try {
    if (
      window.openai?.requestDisplayMode &&
      (window.openai as OpenAIHost).displayMode !== 'inline'
    ) {
      window.openai.requestDisplayMode({ mode: 'inline' })
    }
  } catch { }
  setDisplayMode('inline')
  notifyHeight()
}, [notifyHeight])

Change 3 — Sync displayMode from openai:set_globals
Current code (inside the useEffect):
tsconst handleSetGlobals = () => {
  if (isInitializedRef.current) {
    handleToolOutputUpdate()
  } else {
    loadData()
  }
}
Problem: openai:set_globals carries window.openai.displayMode but the widget never reads it. When native iOS "X" closes fullscreen, host fires set_globals with updated displayMode but widget state never syncs. Split-brain.
Fix:
tsconst handleSetGlobals = () => {
  // Sync displayMode from host (only after init to avoid layout flicker)
  if (isInitializedRef.current) {
    const hostMode = (window.openai as OpenAIHost | undefined)?.displayMode
    if (hostMode === 'fullscreen' || hostMode === 'inline') {
      setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
    }
  }

  if (isInitializedRef.current) {
    handleToolOutputUpdate()
  } else {
    loadData()
  }
}

Change 4 — Diagnostic logging in handleToolOutputUpdate
Add at the top of handleToolOutputUpdate, before the ref guard. Temporary — will be removed in increment 58.
tsif (window.__PG_DEBUG__) {
  console.log('[PG:set_globals]', {
    toolOutputChanged: currentToolOutput !== lastToolOutputRef.current,
    hasToolOutput: !!currentToolOutput,
    hostDisplayMode: (window.openai as OpenAIHost | undefined)?.displayMode,
  })
}
To enable on device: open ChatGPT dev console and run window.__PG_DEBUG__ = true. Off by default — no console spam in production.

Type definition
Define once near the display mode handlers section:
tstype OpenAIHost = {
  displayMode?: 'inline' | 'fullscreen'
  requestDisplayMode?: (opts: { mode: 'inline' | 'fullscreen' }) => void
  toolOutput?: unknown
}
Use OpenAIHost for all casts in Changes 1–4, replacing the ad-hoc { displayMode?: string } casts.

Acceptance criteria

Desktop: "Open Full Dashboard" expands widget layout in-place — no left-panel overlay, no "X" button in top corner.
Desktop: "Minimieren" returns to inline correctly.
iOS: "Open Full Dashboard" transitions to fullscreen.
iOS: "Minimieren" returns to inline without requiring native "X".
iOS: closing fullscreen with native "X" updates widget layout to inline correctly.
[PG:set_globals] log only appears when window.__PG_DEBUG__ = true is set in console.
No changes to any other file.


Pre-deploy
Widget-only. No Alembic checks. After commit: trigger manual Render redeploy. Verify built HTML contains updated handlers before deploying.