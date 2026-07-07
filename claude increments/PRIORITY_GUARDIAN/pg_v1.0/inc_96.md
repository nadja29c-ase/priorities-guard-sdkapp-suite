BRIEFING — inc_pg_widget_meta_fix: Restore top-level _meta widget binding across PG widget tools
App: Priority Guardian V1.0 — published ChatGPT App Store app (mcp_server/priority_guardian/). ChatGPT-SDK canonical artifacts apply.
TOP INSTRUCTION: Requirements only, minimal code — no implementation dictation. Verified-working reference: MindSort-OpenAI mcp_server/clarity/tools/organize_thoughts.py at Jul-1-deployed commit a25811ae (top-level _meta, resources/read fires in prod). STEP 1 is root-cause completion, NOT the fix — do not change code until Step 1 resolves why it used to render.
STEP 1 — RESOLVE THE ROOT CAUSE (mandatory before fixing; per no-fix-without-confirmed-cause):
PG's widget rendered in production previously and passed App Store submission. Current code nests the binding in structuredContent._meta with no top-level _meta — which canon says the host can't see. These are contradictory: if always nested, it could never have rendered. Resolve via git history:

git log -p (or git log --follow -p) on get_priorities.py, focused on the _meta / CallToolResult construction. Determine: was _meta ever at top-level, and did a specific commit move it into structuredContent? On what date, relative to the last confirmed render (Jun 30) and submission?
Report one of: (a) regression — a commit moved _meta off top-level on date X (→ complete confirmed root cause; fix = restore); or (b) always nested — then the host behavior changed and PG's placement was always non-canonical-but-tolerated (→ fix still applies, but note the host-change dimension for the OpenAI ticket).
Do NOT proceed to the fix until this is reported. This answers "how come it used to work" and confirms the cause is complete, not partial.

Root cause (confirmed from source, pending Step 1's regression-vs-host question): widget tools build the binding as structuredContent._meta.openai/outputTemplate with no top-level _meta; the host reads top-level _meta for hydration → no resources/read → no render. Verified in get_priorities.py. MindSort (top-level _meta) renders; the same-platform contrast confirms the divergence.
STEP 2 — SCOPE (verify each; fix if affected):

Confirmed affected: mcp_server/priority_guardian/tools/get_priorities.py
Must verify and fix if affected: mcp_server/priority_guardian/tools/create_priority.py, mcp_server/priority_guardian/tools/render_weekly_report.py
Do NOT touch non-widget tools, MindSort/clarity, Claude apps, Unpack, or backend.

Requirement: each affected tool's CallToolResult must expose the widget binding at top-level _meta (ui.resourceUri + openai/outputTemplate = WIDGET_URI), mirroring MindSort's working shape and OpenAI canon. Preserve structuredContent.data and assistant_guidance. Non-blocking verification: MindSort returns content=[] while PG returns TextContent; per KB, when both content and structuredContent are present the host reads only structuredContent. Verify against canon whether PG's content should change — but do NOT block or gate the fix on this; the confirmed bug is the missing top-level _meta. If canon is silent, keep content as-is and flag for follow-up.
Canonical guidance — READ FRESH (ChatGPT-SDK; your named artifacts):

Openai_uiux.md (c) — authority on _meta placement/hydration. CRITICAL living-artifact flag: this doc is currently NOT reachable in the codebase (it lives in the project KB), so neither Claude Code nor review can git show-verify against it. Fix: copy it into the codebase (docs/). Until then, fall back to OpenAI's official online reference (developers.openai.com/apps-sdk/reference) and state which was used. AND: if Step 1 shows a commit moved _meta into structuredContent, check whether Openai_uiux.md documents the nested pattern — if so, the doc caused the bug; flag and correct it, or every future widget tool repeats it.
Shared Backend Architecture doc (a); Compliance_Master.md (b); ADR_MCP Server implementation standard.md (f); relevant ADRs (e).
ALL OPERATIONS...md (d); read OPERATIONS_PREDEPLOY.md before committing.
Flag any of these unreachable/outdated/mismatched (living-artifact rule) — several KB canonical docs are currently not in the codebase; recommend copying them in.

PUBLISHED-APP DEPLOY-vs-RESUBMIT CHECK (before deploy): This changes tool-result structure on a published app. It passed submission with the previous shape. Determine whether the fix ships via a normal Render deploy or requires submitting a new app version for review (per OpenAI's published-app model). Report which; if resubmission is required, that's the release path — do not assume deploy-alone ships it.
Tests (unit separate from integration):

Unit: per affected tool, assert CallToolResult has top-level _meta with ui.resourceUri and openai/outputTemplate = WIDGET_URI; assert structuredContent.data and assistant_guidance preserved. State per test what bug would still pass it.
Integration: tools/call per tool returns top-level _meta with the binding; a host reading top-level _meta would fetch. Note end-to-end (real ChatGPT resources/read) is confirmable only post-deploy in production — call that out as the post-deploy verification, not a pre-deploy gate.
DB integrity: none (state so).

Production-readiness (published-app context):

Scalability (Scalability & TAM): no change — result-shape only.
GDPR/Data Retention (Data Retention Strategy pdf): moved _meta is a URI/template ref, no PII — verify.
Under load/latency: no change.
The production-readiness that matters here: the widget actually hydrates for real users.

Deployment discipline: read OPERATIONS_PREDEPLOY.md before committing; git stash before working-tree overwrite; end with commit hash; review verifies against git show <hash>:<path>. Post-deploy: capture one production session, confirm resource.read.requested now fires (definitive success signal).
What NOT to do: don't fix before Step 1 resolves the regression-vs-host question; don't restructure tools beyond the binding move; don't gate the fix on the content question; don't touch other apps/backend; don't assume deploy-alone ships it.
Deliverable: Step 1 finding (regression commit+date, or always-nested→host-change); commit hash of the fix; confirmation affected tools expose top-level _meta; deploy-vs-resubmit determination; Openai_uiux.md reachability + did-the-doc-cause-it finding; test evidence; explicit "what I did NOT verify" list; post-deploy resource.read.requested confirmation.

What I verified: get_priorities.py — binding nested, no top-level _meta (from source). What I did NOT verify: the git history of _meta placement (Step 1 — resolves "how come it worked"); the other two widget tools; MindSort at a25811ae myself; Openai_uiux.md (unreadable — flagged); deploy-vs-resubmit.
Direct answer to "how come it used to work": unknown until Step 1's git history is read — and per your top rule, that must be resolved before this counts as a confirmed complete root cause. The most likely answer is a regression: a commit moved _meta off top-level after submission, breaking a widget that previously rendered. If so, that's the clean, complete cause — and the fix restores what worked. That's why Step 1 leads, not the fix.