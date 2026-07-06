BRIEFING — inc_98 (DIAGNOSTIC, published app): Make PG widget-render observable + audit widget _meta/CSP shape
App: Priority Guardian V1.0 — approved, live in the ChatGPT App Store, on production. ChatGPT SDK app; ChatGPT canonical artifacts apply.
TOP INSTRUCTION: This is a diagnostic + observability increment. Do NOT change render logic or _meta values as a "fix" yet. Per the 100%-root-cause rule, we must first make render observable and confirm the cause. The one permitted change is logging levels (DEBUG→INFO) and, if the _meta audit finds a canon violation, that's reported — not silently "fixed" in this increment.
Problem: PG's dashboard widget intermittently fails to render in production ChatGPT. The tool call succeeds and returns _meta.openai/outputTemplate (widget binding present), but the widget intermittently doesn't appear. We cannot currently prove whether ChatGPT fails to issue resources/read (host-side) or whether PG's widget response is defective, because the resource-read logging is at DEBUG and invisible in production.
Verified context (read this session, working tree):

handlers/resources.py: handle_read_resource logs resource.read.requested + resource.read.serving_widget at logger.debug → silent in production (LOG_LEVEL defaults INFO). The widget resource _meta carries two CSP declarations — ui.csp (camelCase, resourceDomains: []) AND openai/widgetCSP (snake_case, with comment "published apps need snake_case form"). WIDGET_VERSION = "" (versionless URI).
handlers/tools.py: tool.dispatch.received at DEBUG; tool.dispatch.executing + tool.timing at INFO (visible). Tool-result outputTemplate binding is emitted inside individual tool handlers (tools/get_priorities.py), not the dispatcher.
PG already has tools/widget_tools/record_widget_diagnostic.py — prior widget-diagnostic infrastructure; check whether instrumentation should extend it.

Goal: Produce a binary, log-based verdict on the render failure by making the render path observable, and audit whether PG's widget _meta/CSP shape is correct for a published app per Openai_uiux.md.
Canonical guidance — READ FRESH before implementing:

Openai_uiux.md — THE authority for widget _meta, CSP form, outputTemplate, and OpenAI design tokens. Specifically confirm: is the dual ui.csp + openai/widgetCSP declaration correct/required for a published app, or is one form stale? Is empty resourceDomains correct given the widget's actual asset needs? Report any mismatch (do NOT fix in this increment).
"Priority Guard App Suite: Shared Backend — Architecture…"
Compliance_Master.md; ADR_MCP Server implementation standard.md; relevant ADRs.
ALL OPERATIONS...md; read OPERATIONS_PREDEPLOY.md before committing (published app — full pre-deploy discipline).
Flag any doc unreachable/mismatched (living-artifact rule).

Work items (requirements — minimal code):

Promote render-path logging to INFO so production shows, per session, whether the widget resource was fetched: resource.read.requested and resource.read.serving_widget (currently DEBUG) → INFO; and add/confirm an INFO-level distinct event for resources/read vs resources/list vs resources/templates/list routing (check server.py dispatch). Also confirm tools/call is INFO-visible (it is, via tool.dispatch.executing). Goal: a production log for one session unambiguously shows tool-call-happened + resource-read-happened-or-not. Log method/URI/html_length only — no user data, no PII.
Audit (report-only) the widget _meta/CSP shape against Openai_uiux.md: dual CSP forms, resourceDomains: [] correctness, outputTemplate consistency between the tool result (get_priorities.py) and the resource _meta (resources.py) — the tool's outputTemplate URI must exactly match the served resource URI (constants.py WIDGET_URI). Report findings; do NOT change _meta in this increment.
Confirm versionless URI implications: WIDGET_VERSION = "" means the widget URI never changes across deploys → ChatGPT resource cache may never invalidate (KB footgun: cache invalidation needs delete-and-re-add). Report whether this is a render-staleness risk; do not change.

Tests (unit separate from integration):

Unit: the promoted log events fire at INFO on a simulated resources/read for the widget URI and for an unknown URI (assert event emitted with correct URI/level; no PII). Assert the tool-result outputTemplate URI equals constants.WIDGET_URI (consistency guard — catches drift between tool binding and served resource).
Integration: against a running PG server, issue a resources/read for the widget → assert the INFO log appears and the widget HTML is served; issue tools/call get_priorities → assert INFO dispatch log. Confirm the two are distinguishable in logs for a session.
DB integrity: none (state explicitly).

Production-readiness (published-app context):

Scalability (Scalability & TAM): logging-level change only; negligible. Ensure promoted logs don't dump large payloads (log html_length, not HTML).
GDPR/Data Retention: the promoted logs must contain NO user data/PII — URIs, lengths, method names only. Critical on a published app.
Under load/latency: no render-path behavior change; logging is cheap.

Deployment discipline: Read OPERATIONS_PREDEPLOY.md before committing. git stash before any working-tree overwrite. Reviewed round ends with a commit hash; review verifies against git show <hash>:<path>.
What NOT to do: No render-logic or _meta-value changes (audit reports them; fixes are a separate increment gated on confirmed cause). No touching MindSort/Clarity, Claude apps, Unpack, backend. No new widget version bump in this increment.
Deliverable: commit hash; confirmation the render-path events now log at INFO in production; the _meta/CSP audit findings vs Openai_uiux.md; the versionless-URI staleness assessment; explicit "what I did NOT verify" list.
The verdict this enables (next step after deploy): with INFO logging live, reproduce a PG non-render in production and read the session logs:

tools/call present, resources/read absent → host-side (ChatGPT didn't fetch) → escalate to OpenAI with published-app evidence + workarounds; no server fix exists.
resources/read present, widget still absent → client/_meta-side → the _meta/CSP audit findings become the fix candidate (separate increment).
The audit independently may find a canon violation (dual CSP / empty resourceDomains) that explains intermittency regardless.


What I did NOT verify this session (per your rule, explicit): I did NOT read tools/get_priorities.py (the tool-result outputTemplate emission), tools/widget_tools/constants.py (WIDGET_URI value), server.py (the MCP request dispatch / how resources/read is routed and whether request-type logging exists there), or Openai_uiux.md (the CSP-form authority) — the briefing instructs Claude Code to read these as part of the scoped work, and I flag that my "dual CSP may be wrong" is a red-flag to investigate against canon, NOT a confirmed defect. I read handlers/resources.py and handlers/tools.py in full. Could not run git show/bash against the spaced path — Claude Code performs git-pinned reads and returns the hash.
Strategic note, per your rules — and I'll be direct: this is legitimate work — a real user-facing render issue on your published, revenue app, and it lacked the observability to diagnose. Instrumenting it is correct. But hold the discipline: the most likely outcome, per everything this thread established, is "resources/read absent → host-side → escalate, no server fix." The value of inc_98 is that it will prove which branch you're in with one production session, instead of another week of inference. If it confirms host-side, escalate and stop — don't let it spawn another render-chasing thread on a platform bug you can't fix. And the _meta/CSP audit is the one genuinely in-your-control lead; if canon says PG's dual-CSP/empty-resourceDomains shape is wrong, that's a real fix worth making. Either way: instrument → observe one real failure → act on the branch. That terminates the render investigation instead of perpetuating it.