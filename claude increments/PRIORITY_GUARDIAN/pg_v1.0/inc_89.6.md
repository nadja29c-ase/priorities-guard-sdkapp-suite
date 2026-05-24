CSP confirmed. The manual fetch test got BLOCKED Failed to fetch with the exact same CSP violation. Diagnosis is now 100% certain: connect-src directive in the sandbox CSP doesn't include your shared backend domain.
Direct fix. Want me to write Inc 89.6 as a formal briefing, or push the change directly?
Either way, here's the exact code change for handlers/resources.py:
Three locations, same pattern. Find every occurrence of:
python"csp": {
    "connectDomains": [],  # Widget uses callTool/postMessage, not HTTP
    "resourceDomains": [],
Replace with:
python"csp": {
    "connectDomains": [BACKEND_DOMAIN],  # widget-error and widget-diagnostic endpoints
    "resourceDomains": [],
Three occurrences: list_resources(), list_resource_templates(), handle_read_resource().
BACKEND_DOMAIN is already defined at the top of the file as _extract_origin(BACKEND_URL) → resolves to https://priorities-guard-sdkapp-suite.onrender.com.

Two things to flag separately:
1. Inc 83's widget-error endpoint has been silently broken since it shipped. Same CSP wall blocks reportWidgetError. Any production user who hit a widget error in the past month got their error logged client-side and silently dropped at the iframe boundary. Worth verifying: search Better Stack for widget.error events from production users. If zero — Inc 83's reporter never worked, only the test fixtures did. Add to the cleanup list for after Inc 89 is fully resolved.
2. OPERATIONS_PREDEPLOY.md needs a post-deploy CSP check. The structural lesson from today: when a widget makes a new outbound fetch(), the CSP needs to be updated to match. There's no Python-side test that catches this — only a production iframe check would. Add to the "Widget Bundle Changes" section a post-deploy verification step:

After widget-side code introduces any new fetch(), WebSocket, or other outbound network call, verify in the production iframe console: open DevTools, trigger the code path that calls the new endpoint, check for CSP Refused to connect errors. If any appear, the domain must be added to _meta.ui.csp.connectDomains in handlers/resources.py (three locations: list_resources, list_resource_templates, handle_read_resource).


My recommendation: push the three-line change directly. It's small enough that a formal briefing is overhead. But also make these followup notes:

Open a ticket: "Inc 83 widget-error reporter likely never delivered events to backend — verify and document"
Update OPERATIONS_PREDEPLOY.md "Widget Bundle Changes" section with the new CSP check (per above)
After Inc 89 fully resolves and we have diagnostic data, revisit whether the CSP debt has caused other silent failures

Push the fix?You said: yesyes3:50 PMClaude responded: Let me first read the current state of handlers/resources.Let me first read the current state of handlers/resources.py so I can give Claude Code precise instructions, not just a pattern.Read Text FileRead Text FileThree exact locations confirmed. Here are the precise instructions for Claude Code:

Inc 89.6 — CSP fix: allow widget→backend connections
Type: Bug fix. One file, three identical changes. No behavior change beyond unblocking the already-shipped diagnostic POSTs (and the Inc 83 widget-error POSTs that have likely been silently failing).
Root cause: _meta.ui.csp.connectDomains is [] in handlers/resources.py. The widget calls fetch() to priorities-guard-sdkapp-suite.onrender.com for diagnostic and error reporting. The sandbox iframe enforces connect-src strictly per this CSP declaration. Empty array = no external connections allowed. Every diagnostic POST is being silently blocked (63 CSP violation errors confirmed in production iframe DevTools at 13:48 UTC today).
File touched: mcp_server/priority_guardian/handlers/resources.py only.
Edits
Three locations, identical replacement.
Location 1 — inside list_resources() (around line 80):
Find:
python                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],  # Widget uses callTool/postMessage, not HTTP
                        "resourceDomains": [],  # Self-contained HTML, no external assets
                    },
                },
Replace with:
python                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [BACKEND_DOMAIN],  # widget-error (Inc 83) + widget-diagnostic (Inc 89) endpoints
                        "resourceDomains": [],  # Self-contained HTML, no external assets
                    },
                },
Location 2 — inside list_resource_templates() (around line 105):
Find:
python                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],
                        "resourceDomains": [],
                    },
                },
Replace with:
python                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [BACKEND_DOMAIN],  # widget-error + widget-diagnostic endpoints
                        "resourceDomains": [],
                    },
                },
Location 3 — inside handle_read_resource() (around line 142):
Find:
python        resource_meta = {
            "ui": {
                "domain": WIDGET_DOMAIN,
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": [],
                },
            },
Replace with:
python        resource_meta = {
            "ui": {
                "domain": WIDGET_DOMAIN,
                "csp": {
                    "connectDomains": [BACKEND_DOMAIN],  # widget-error + widget-diagnostic endpoints
                    "resourceDomains": [],
                },
            },
Out of scope

No changes to WIDGET_URI. Stays at v12 (constants.py untouched).
No changes to openai/widgetCSP.redirect_domains. That's a legacy field for openExternal, unrelated.
No changes to widget source code. The widget bundle on disk is unchanged.
No rebuild of the widget. Pure server-side CSP advertisement change.

Pre-deploy
Read doc/OPERATIONS_PREDEPLOY.md per project rules.
Verify the change:
bashgrep -n 'connectDomains' mcp_server/priority_guardian/handlers/resources.py
Should show three lines, all with [BACKEND_DOMAIN], none with [].
Verify BACKEND_DOMAIN resolves correctly:
bashpython -c "
from mcp_server.priority_guardian.handlers.resources import BACKEND_DOMAIN
print(BACKEND_DOMAIN)
"
Must print https://priorities-guard-sdkapp-suite.onrender.com exactly.
Deploy
PG MCP service does NOT auto-deploy on push (confirmed today). Manual deploy required:

Push commit
Render dashboard → PG MCP service → Manual Deploy → Deploy latest commit
Wait for "Deploy live" (~2-4 min)
Verify PG MCP logs show mcp.server.startup event with current timestamp

Post-deploy verification

Cache-bust dance: ChatGPT Settings → Apps → Priority Guardian → Refresh, then new conversation.
In iframe console, run the manual fetch test:

javascript   fetch("https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-diagnostic", {
     method: "POST",
     headers: {"Content-Type": "application/json"},
     body: JSON.stringify({event: "manual-csp-test", data: {}})
   }).then(r => console.log("OK", r.status)).catch(e => console.log("BLOCKED", e.message))
Expected: OK 204. If still BLOCKED, the CSP didn't propagate — investigate.

Reproduce the bug: click "Open full dashboard" once.
Check shared backend Render logs for widget.diagnostic events in the past minute. Expect at minimum a mount event, plus set_globals and displayMode.change events.
If diagnostic events appear: Inc 89 is finally functional. Group by sid, analyze hypothesis H1/H2/H3/H4 from the original Inc 89 briefing, write the fix briefing.

Followup work (not part of this increment)

Inc 83 silent failure: The widget-error endpoint has had the same CSP problem since it shipped. Verify in Better Stack: search for any widget.error events from production users. If zero → confirm Inc 83 reporter never delivered events from real users, only from local test fixtures.
Update OPERATIONS_PREDEPLOY.md "Widget Bundle Changes" section. Add post-deploy CSP check:

When the widget makes any new outbound fetch() / WebSocket / etc., the target domain must be added to _meta.ui.csp.connectDomains in three places in handlers/resources.py. Verify in production iframe DevTools console: trigger the code path, check for Refused to connect errors. No Python test catches this — only an iframe check.


Investigate other silent CSP-blocked features: Any other widget code that makes fetch() to non-MCP endpoints will be blocked. Audit widget source for fetch(, XMLHttpRequest, new WebSocket(, EventSource. Document findings.


Push it. After deploy verifies, reproduce the fullscreen bug and send me the widget.diagnostic events from Better Stack/Render. Then we finally diagnose the original bug.