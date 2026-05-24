Inc 89.7 — Add legacy openai/widgetCSP.connect_domains
Type: Bug fix. One file, three identical edits.
Why: Inc 89.6 added _meta.ui.csp.connectDomains (the new camelCase form). CSP violations persist after deploy — the new form is being ignored by ChatGPT's published-app pipeline. OpenAI's reference docs state both the legacy _meta["openai/widgetCSP"] snake_case form and the new _meta.ui.csp camelCase form are supported; community evidence suggests published apps may need the legacy form specifically. We try the legacy form before resorting to architectural changes.
What this does NOT decide: whether the legacy form will work either. There's an open OpenAI GitHub issue (#85, October 2025) claiming connect_domains is hardcoded-ignored, but it's old enough that it may have been silently resolved. If this fix doesn't work, next increment switches diagnostic reporting to window.openai.callTool() and bypasses browser CSP entirely.
Edits
File: mcp_server/priority_guardian/handlers/resources.py. Three locations.
Each location currently has:
python"openai/widgetCSP": {
    "redirect_domains": [BACKEND_DOMAIN],
},
Change to:
python"openai/widgetCSP": {
    "connect_domains": [BACKEND_DOMAIN],
    "resource_domains": [],
    "redirect_domains": [BACKEND_DOMAIN],
},
Note the snake_case keys — connect_domains not connectDomains. This is the legacy ChatGPT format. The new _meta.ui.csp.connectDomains (camelCase, added in Inc 89.6) stays as-is. Belt and suspenders: both forms declared, in case the published-app pipeline reads only one.
Three locations:

list_resources() — inside the single Resource in the returned list, under _meta["openai/widgetCSP"]
list_resource_templates() — inside the single ResourceTemplate, same key
handle_read_resource() — inside resource_meta dict, same key

Use exact text-replace. Each location currently shows "redirect_domains": [BACKEND_DOMAIN] as the only key inside openai/widgetCSP — replace with the three-key version above.
Out of scope

No changes to _meta.ui.csp.connectDomains (the new form Inc 89.6 added). Leaves both forms in place.
No changes to WIDGET_URI. Stays v12.
No widget source changes. Bundle stays as-is.
No rebuild. Server-side only.

Pre-deploy
Verify the change:
bashgrep -A 4 'openai/widgetCSP' mcp_server/priority_guardian/handlers/resources.py
Should show three blocks, each containing connect_domains, resource_domains, redirect_domains — all three keys.
Deploy
PG MCP requires manual deploy on Render (no auto-deploy). Push, then trigger manual deploy.
Post-deploy verification

Wait for "Deploy live" status on Render.
Cache-bust dance: Settings → Apps → Priority Guardian → Refresh, new conversation.
Iframe console — run the manual fetch test:

javascript   fetch("https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-diagnostic", {
     method: "POST",
     headers: {"Content-Type": "application/json"},
     body: JSON.stringify({event: "manual-test-89-7", data: {}})
   }).then(r => console.log("OK", r.status)).catch(e => console.log("BLOCKED", e.message))

Two possible outcomes:

OK 204 → legacy CSP form works. Reproduce the fullscreen bug, then check shared backend Render logs for widget.diagnostic events. Continue with Inc 89's original purpose.
BLOCKED Failed to fetch → Issue #85 still active. Move to Inc 89.8 (rewrite reporter to use window.openai.callTool()).



If 89.7 works
Followup notes:

Document in OPERATIONS_PREDEPLOY.md that published apps require the legacy openai/widgetCSP.connect_domains form, not just _meta.ui.csp.connectDomains. The OpenAI docs say either works but in practice the legacy form is what gets enforced for already-approved apps.
Inc 83's widget-error reporter likely had the same silent failure — once 89.7 ships, verify Better Stack starts receiving widget.error events from production.

If 89.7 doesn't work
Inc 89.8 briefing pre-decision:

Switch widgetErrorReporter.ts reportWidgetDiagnostic from fetch() to window.openai.callTool('record_widget_diagnostic', {event, data, sid, ts}).
Add a new private MCP tool record_widget_diagnostic (visibility: app-only, no widget URI) that takes the diagnostic payload as arguments and writes to the same Better Stack logger.
This routes the data through the MCP bridge, which is not subject to iframe CSP.
More code change but mechanically can't be blocked by browser CSP.


Push it. Direct test after deploy will tell us if we're back in business or need 89.8.