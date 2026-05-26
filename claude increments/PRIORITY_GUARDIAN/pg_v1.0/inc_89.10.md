Inc 89.10 — Desktop fullscreen intent guard (Option B)
Type: Production fix. Single-file React change in App.tsx. Pure dev-mode-first; ships to OpenAI in v15 submission alongside Inc 89.6/89.7/89.8/89.9.
Why
Inc 89.9 dev-mode capture (session pg-1779704455582-k6pwhf, build 2026-05-25T10:13:44Z) empirically confirmed H2. The 18ms gap between user click and host revert is documented in the diagnostic event stream:

t=7251.2ms: handleExpandToFullscreen fires (isMobile: false → no host call)
t=7269.4ms (+18ms): host fires set_globals(hostMode: "inline")
t=7269.4ms: handleSetGlobals.hostSync calls setDisplayMode('inline') → revert

Additional set_globals(inline) bursts captured at t=7277ms, 13837ms, 13838ms, 14168ms, 14169ms — confirming a time-based guard window won't hold, because host fires inline events seconds after click. The fix must persist for the lifetime of the local fullscreen session.
Architecture rationale
Desktop fullscreen in PG is owned by the widget, not the host. handleExpandToFullscreen does NOT call requestDisplayMode on desktop (only on mobile). Host displayMode therefore stays 'inline' for the entire desktop "fullscreen" session. Any set_globals(hostMode: 'inline') is stale by definition on desktop while local fullscreen is intended.
Mobile is unchanged: there, fullscreen IS host-driven (requestDisplayMode({ mode: 'fullscreen' })), and host sync is correct behavior.
The guard scope: ONLY desktop, ONLY when local fullscreen intent is active, ONLY for hostMode === 'inline'. Mobile path untouched. Host fullscreen sync untouched.
Implementation Approach — Copy and Adjust, Never Rewrite
Make ONLY the changes listed below in App.tsx. Do not restructure, refactor, or "improve" any other code in the file. Do not change variable names, comments, or formatting outside the explicit edits. If anything looks like it could be improved that is NOT listed here, leave it alone.

Edits to mcp_server/priority_guardian/widget-react/src/App.tsx
Edit 1: Add the intent ref
Find the existing comment block declaring refs for fullscreen tracking. Locate this section (around line ~90):
tsx  // Tracks whether fullscreen was entered specifically for the add form (mobile only).
  // Used to reverse the fullscreen on form close without affecting user-initiated fullscreen.
  const enteredFullscreenForAddRef = useRef(false)

  // Tracks whether fullscreen was entered specifically for editing (mobile only). (Inc 71)
  const enteredFullscreenForEditRef = useRef(false)
  const wasEditingRef = useRef<string | null>(null)
Immediately AFTER wasEditingRef, add:
tsx  // Inc 89.10: desktop-local fullscreen intent guard.
  // Desktop fullscreen is owned by the widget (no requestDisplayMode call).
  // Host displayMode stays 'inline' during desktop local-fullscreen sessions.
  // When true, ignore host set_globals(hostMode: 'inline') syncs that would revert
  // local fullscreen. Cleared by handleMinimizeToInline. Mobile is unaffected.
  const desktopLocalFullscreenIntentRef = useRef(false)
Edit 2: Set the flag in handleExpandToFullscreen
Find the existing handler:
tsx  const handleExpandToFullscreen = useCallback(() => {
    if (isMobile) {
      try {
        if (
          window.openai?.requestDisplayMode &&
          (window.openai as OpenAIHost).displayMode !== 'fullscreen'
        ) {
          window.openai.requestDisplayMode({ mode: 'fullscreen' })
        }
      } catch { /* noop */ }
    }
    logDisplayModeChange('fullscreen', 'handleExpandToFullscreen', { isMobile })
    setDisplayMode('fullscreen')
    notifyHeight()
  }, [isMobile, notifyHeight])
Add intent-set immediately after the if (isMobile) { ... } block, BEFORE logDisplayModeChange. New version:
tsx  const handleExpandToFullscreen = useCallback(() => {
    if (isMobile) {
      try {
        if (
          window.openai?.requestDisplayMode &&
          (window.openai as OpenAIHost).displayMode !== 'fullscreen'
        ) {
          window.openai.requestDisplayMode({ mode: 'fullscreen' })
        }
      } catch { /* noop */ }
    } else {
      // Inc 89.10: desktop fullscreen is local-only; mark intent so handleSetGlobals
      // ignores stale host inline syncs until the user explicitly minimizes.
      desktopLocalFullscreenIntentRef.current = true
    }
    logDisplayModeChange('fullscreen', 'handleExpandToFullscreen', { isMobile })
    setDisplayMode('fullscreen')
    notifyHeight()
  }, [isMobile, notifyHeight])
Edit 3: Clear the flag in handleMinimizeToInline
Find the existing handler:
tsx  const handleMinimizeToInline = useCallback(() => {
    if (isMobile) {
      try {
        if (
          window.openai?.requestDisplayMode &&
          (window.openai as OpenAIHost).displayMode !== 'inline'
        ) {
          window.openai.requestDisplayMode({ mode: 'inline' })
        }
      } catch { /* noop */ }
    }
    logDisplayModeChange('inline', 'handleMinimizeToInline', { isMobile })
    setDisplayMode('inline')
    notifyHeight()
  }, [isMobile, notifyHeight])
Add clear-intent symmetrically. New version:
tsx  const handleMinimizeToInline = useCallback(() => {
    if (isMobile) {
      try {
        if (
          window.openai?.requestDisplayMode &&
          (window.openai as OpenAIHost).displayMode !== 'inline'
        ) {
          window.openai.requestDisplayMode({ mode: 'inline' })
        }
      } catch { /* noop */ }
    } else {
      // Inc 89.10: user explicitly closing local fullscreen — release the guard
      // so subsequent host inline syncs work normally.
      desktopLocalFullscreenIntentRef.current = false
    }
    logDisplayModeChange('inline', 'handleMinimizeToInline', { isMobile })
    setDisplayMode('inline')
    notifyHeight()
  }, [isMobile, notifyHeight])
Edit 4: Guard the sync path in handleSetGlobals
Find the existing block in the useEffect(() => { loadData(); const handleSetGlobals = () => { ... } }):
tsx        if (hostMode === 'fullscreen' || hostMode === 'inline') {
          // Inc 89: log the sync intent before it fires
          logDisplayModeChange('sync', 'handleSetGlobals.hostSync', { hostMode })
          setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
        }
Replace with:
tsx        if (hostMode === 'fullscreen' || hostMode === 'inline') {
          // Inc 89.10: desktop-local fullscreen intent guard.
          // On desktop, when the user has opened local fullscreen, host displayMode
          // stays 'inline' (because we never called requestDisplayMode). Any host
          // set_globals(inline) during this period is stale and would revert the
          // user's intended fullscreen. Mobile and host 'fullscreen' syncs are
          // never blocked.
          const isStaleDesktopInlineSync =
            hostMode === 'inline' &&
            !isMobile &&
            desktopLocalFullscreenIntentRef.current

          if (isStaleDesktopInlineSync) {
            // Log the ignored sync for dev-mode and v15 production verification.
            logDisplayModeChange('sync-ignored', 'handleSetGlobals.intentGuard', { hostMode })
          } else {
            // Inc 89: log the sync intent before it fires
            logDisplayModeChange('sync', 'handleSetGlobals.hostSync', { hostMode })
            setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
          }
        }

Out of scope
Explicitly NOT in this increment:

WIDGET_URI bump (stays v12 for this dev-mode iteration; bump happens as part of v15 submission packaging, separate increment)
Removing or gating diagnostics (PG_DIAG_FULLSCREEN, logDisplayModeChange, reportWidgetDiagnostic). Diagnostics MUST stay on for v15 to verify the fix in production. Cleanup happens in a later increment AFTER v15 is approved AND the fix is verified by production diagnostic events.
Cap reduction in widgetErrorReporter.ts (stays at 200, as set in Inc 89.9)
Any architectural change to mobile fullscreen behavior
Any change to the diagnostic reporter, the record_widget_diagnostic MCP tool, or backend storage
Tool schemas, scopes, external domains — no changes
The "ChatGPT host fires set_globals on Android UA at t=14168ms even though the test browser is Mac Chrome" curiosity — interesting but not blocking. Track separately if it ever matters.


Pre-deploy
This is a dev-mode iteration. No production deploy. Read OPERATIONS.md / OPERATIONS_PREDEPLOY.md before any deployment in case of additional pre-deploy tasks.
bash# 1. Verify the ref was added
grep -n "desktopLocalFullscreenIntentRef" mcp_server/priority_guardian/widget-react/src/App.tsx
# Expect 4 hits: declaration + set in expand + clear in minimize + guard check in handleSetGlobals

# 2. Verify the sync-ignored caller string is in place
grep -n "handleSetGlobals.intentGuard" mcp_server/priority_guardian/widget-react/src/App.tsx
# Expect 1 hit

# 3. Lint + typecheck
cd mcp_server/priority_guardian/widget-react && npm run lint && npx tsc --noEmit
cd -

# 4. Run existing widget tests — none should break (no new test cases required for this increment;
#    behavior is covered by dev-mode validation below)
cd mcp_server/priority_guardian/widget-react && npm test
cd -

# 5. Rebuild widget bundle
cd mcp_server/priority_guardian/widget-react && npm run build
cd -

# 6. Verify the rebuild produced new output with current timestamp
ls -la mcp_server/priority_guardian/widgets/pg-dashboard.html

Deploy (dev mode only for this increment)

Push commit (widget source + rebuilt bundle).
Wait for Render to deploy the MCP server.
In ChatGPT app: Settings → Apps → (dev-mode PG entry) → Refresh.
Start a NEW conversation (cached widget state from previous session does not carry over).


Post-deploy verification
Reproduce the original bug scenario:

Trigger a tool call that renders PG widget ("show me my priorities")
Wait ~3 seconds for mount-time set_globals storm to settle
Click "Open full dashboard" ONCE
Widget should expand to fullscreen and stay expanded
Wait ~10 seconds — widget should remain fullscreen even as host fires intermittent set_globals(inline) events in the background
Click the Minimize button (FullscreenHeader's X)
Widget should collapse to inline and stay inline

Expected diagnostic event sequence
Pull widget.diagnostic events from PG MCP Render logs, filter by latest sid, sort by ts:
mount {initialDisplayMode: "inline", hostMode: "inline", widgetBuildTime: <new>}
set_globals × N {hostMode: "inline"}                       [mount storm]
displayMode.change × N {caller: "handleSetGlobals.hostSync", hostMode: "inline"}  [mount storm syncs]
... (silent waiting for user click) ...
displayMode.change {caller: "handleExpandToFullscreen", isMobile: false, next: "fullscreen"}  [USER CLICK]
set_globals {hostMode: "inline"}                            [host immediately fires]
displayMode.change {caller: "handleSetGlobals.intentGuard", next: "sync-ignored", hostMode: "inline"}  [GUARD FIRED ✓]
... (host may fire more set_globals(inline) over next seconds) ...
set_globals {hostMode: "inline"}
displayMode.change {caller: "handleSetGlobals.intentGuard", next: "sync-ignored", hostMode: "inline"}  [GUARD FIRED ✓]
... (eventually) ...
displayMode.change {caller: "handleMinimizeToInline", isMobile: false, next: "inline"}  [USER MINIMIZE]
set_globals {hostMode: "inline"}
displayMode.change {caller: "handleSetGlobals.hostSync", hostMode: "inline"}  [normal sync resumes]
The KEY signal that confirms the fix works: after handleExpandToFullscreen, every subsequent set_globals(inline) produces a sync-ignored event from handleSetGlobals.intentGuard, NOT a sync event from handleSetGlobals.hostSync. The widget visually stays fullscreen.
What failure would look like
If the fix is wrong:

handleSetGlobals.hostSync fires after the click → the guard wasn't applied → revert still happens. Bug present.
handleSetGlobals.intentGuard fires continuously even AFTER minimize → the clear path is broken → next expand on same session might still work but the symmetry is wrong. Audit.

If diagnostics show no events after the click → cap exhausted again (shouldn't happen at 200) or the new bundle didn't deploy.

After dev-mode verification passes
This fix becomes one of the line items in the v15 OpenAI submission alongside:

Inc 89.6/89.7 CSP declarations (best-effort, ignored today but correct)
Inc 89.8 callTool diagnostic infrastructure (already in this bundle)
Inc 89.9 diagnostic cap at 200 (already in this bundle)
WIDGET_URI bump from v12 → v15 (done as a packaging step before submission)
Brief release notes: "fix to desktop fullscreen display mode reliability + diagnostic infrastructure for future iteration"


Risk assessment
Low. Single-file React change. Two refs, two guard branches, no logic restructuring. Mobile path unchanged. Host fullscreen sync unchanged. Failure mode if the guard logic has a bug: same as today (widget reverts on host inline sync) — no regression possible. The flag is per-component-instance so each widget mount starts fresh.
Edge case considered: widget unmount/remount with intent active. On remount, fresh ref defaults to false. Initial useState reads window.openai.displayMode which is 'inline' on desktop. State and intent both start inline. Clean restart.
Edge case considered: user clicks expand, then page navigation causes widget unmount before clicking minimize. Ref dies with the component. No leak. Next mount starts clean.

Effort

Code change: ~20 lines added across 4 edit locations in App.tsx
Build + dev-mode redeploy: ~3 minutes
Verification: ~5 minutes for one clean repro
Total: ~15 minutes


Push it. Refresh dev mode. Reproduce. Send me the diagnostic events showing the sync-ignored pattern. Once confirmed, this gets bundled into v15 with the URI bump.