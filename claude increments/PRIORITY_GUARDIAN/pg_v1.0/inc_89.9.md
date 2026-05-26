Inc 89.9 — Raise diagnostic cap to capture flash-revert sequence
Type: Diagnostic instrumentation widening. Single-file change + matching test update.
Why: Dev mode reproduction at 09:59 UTC today produced a clean diagnostic stream showing the click event (displayMode.change caller=handleExpandToFullscreen, isMobile=false) at t=2768ms, but zero events after the click. The 20-event session cap was exhausted by a set_globals storm during the first ~33ms of widget mount (~9 set_globals + ~9 hostSync events). The actual revert sequence we need to capture happens AFTER the click. We need budget left to see it.
Confirmed by data:

isMobile: false on click → H1 (mobile misdetection) is REJECTED
H2 (host set_globals overwrites local fullscreen) cannot be confirmed yet because the revert events are missing
Inc 89.8 callTool pipe works perfectly: all 19 dispatches returned 200, structlog events landed in PG MCP logs

Goal: Capture the full event sequence from mount through ~5 seconds after the user click. We need to see whether set_globals(hostMode: inline) and handleSetGlobals.hostSync fire after handleExpandToFullscreen, and if so, how soon.

Edits
File: mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts
Single constant change in the diagnostic section.
Find:
tsconst MAX_DIAGNOSTIC_EVENTS_PER_SESSION = 20
Replace with:
tsconst MAX_DIAGNOSTIC_EVENTS_PER_SESSION = 200
That's the only production code change. No new fields, no logic changes, no new tools.
File: mcp_server/priority_guardian/widget-react/src/__tests__/widgetErrorReporter.test.ts
The existing test enforces per-session cap of 20 diagnostics hardcodes 20. Update it to match the new cap.
Find:
tsit('enforces per-session cap of 20 diagnostics', async () => {
    // Send 21 diagnostic events
    for (let i = 1; i <= 21; i++) {
      await reportWidgetDiagnostic({ event: `event-${i}` })
    }
Replace with:
tsit('enforces per-session cap of 200 diagnostics', async () => {
    // Send 201 diagnostic events
    for (let i = 1; i <= 201; i++) {
      await reportWidgetDiagnostic({ event: `event-${i}` })
    }
Update the assertion in the same test to expect 200 calls instead of 20. Locate expect(mockCallTool).toHaveBeenCalledTimes(20) in the test body and change to expect(mockCallTool).toHaveBeenCalledTimes(200).
No other test changes needed.

Out of Scope

No production fix yet. We're not implementing the intent guard / H2 fix in this increment. We need to confirm H2 first by observing the revert sequence.
No changes to App.tsx — the existing logDisplayModeChange and set_globals logging is sufficient.
No changes to WIDGET_URI. Stays v12.
No changes to the diagnostic tool (record_widget_diagnostic). Server-side handler stays as-is.


Pre-deploy
This is dev-mode only. No production deploy.
bash# Verify the change
grep -n "MAX_DIAGNOSTIC_EVENTS_PER_SESSION" mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts
# Should show one line: MAX_DIAGNOSTIC_EVENTS_PER_SESSION = 200

# Run widget tests
cd mcp_server/priority_guardian/widget-react && npm test -- widgetErrorReporter
cd -

# Rebuild widget
cd mcp_server/priority_guardian/widget-react && npm run build
cd -

# Verify the built bundle contains the new cap
grep -c "200" mcp_server/priority_guardian/widgets/pg-dashboard.html
# Should be > 0 (the value 200 appears somewhere in the inlined JS)

Deploy (dev mode)

Push commit (widget source + rebuilt bundle).
Dev mode does NOT require new submission. Per OpenAI_Support's documented behavior, dev-mode PG fetches fresh widget on Refresh + new conversation.
In ChatGPT app: Settings → Apps → (your dev-mode PG entry) → click Refresh.
Start a new conversation.


Post-deploy verification (the actual debug)

Verify new bundle is running. In iframe console, look for the mount diagnostic event in PG MCP logs. The widgetBuildTime field should be the timestamp from this rebuild (newer than 2026-05-24T14:36:22.530Z).
Capture the repro:

Trigger a tool call that renders PG widget ("show me my priorities")
Wait ~3 seconds for any mount-time set_globals storm to settle
Click "Open full dashboard" ONCE
Wait ~5 seconds (let the flash-revert happen, let any follow-up events fire)
Do NOT click anything else


Pull diagnostic events from PG MCP service Render logs, filtered to last 5 minutes. Grep for widget.diagnostic.
Group by sid (the session id assigned at mount). One repro = one sid.
Sequence by client_ts (or ts since mount).
Look specifically at events AFTER the handleExpandToFullscreen event. What we expect to see if H2 is correct:

   t=2768ms: displayMode.change(caller: handleExpandToFullscreen, isMobile: false, next: fullscreen)
   t=2768-3268ms: set_globals(hostMode: inline)        ← HOST FIRES
   t=2768-3268ms: displayMode.change(caller: handleSetGlobals.hostSync, hostMode: inline)  ← THE REVERT
If we see this sequence → H2 confirmed.
If we see set_globals(hostMode: inline) but NO hostSync event → React state didn't actually revert via our sync path; the revert is happening some other way (host CSS forcing iframe size while React state stays fullscreen).
If we see NO set_globals after the click → revert is happening without any host event at all. Need different hypothesis.

If H2 is confirmed
Next increment (Inc 89.10): implement the intent-guard fix per the design ChatGPT proposed:

Track localFullscreenIntentAtRef.current = performance.now() when handleExpandToFullscreen is called on desktop
In handleSetGlobals, if hostMode === 'inline' AND !isMobile AND performance.now() - localFullscreenIntentAtRef.current < 1000, ignore the sync (log it as sync-ignored for verification)
Otherwise, sync normally

This preserves legitimate host-driven close behavior while protecting the desktop expand window from the race.
If H2 is NOT confirmed
We have a different bug shape. Possibilities:

Host is forcing iframe size via CSS / viewport without firing set_globals
Some other React lifecycle event is calling setDisplayMode('inline')
The widget is being remounted entirely
Something we haven't considered

In that case, we plan a different diagnostic (likely instrumenting all setDisplayMode calls and observing iframe dimensions directly).

Risk
Minimal. One constant change. Tests update accordingly. Reverting is trivial.

Effort

Code change: 1 line
Test update: 2 lines (test name + assertion count)
Widget rebuild: ~30 seconds
Dev-mode redeploy: ~2 minutes
Repro + log collection: ~3 minutes
Total: ~10 minutes


Push it, refresh dev mode, reproduce, send the new event stream. With 200 budget, we'll see exactly what happens in the ~5 seconds after the click.