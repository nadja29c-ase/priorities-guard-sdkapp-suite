You're right — you asked me to emit the final briefing and I ended on a "want me to?" instead of delivering it. Here it is, amended with both deltas (side-effect-free diagnostic tool; MindSort-dev-first phasing) and ChatGPT's do-not-fix instruction up front.

BRIEFING: Diagnostic increment — isolate PG/MindSort widget-non-render root cause
TOP INSTRUCTION — READ FIRST: Do NOT implement a fix. Implement only observability + controlled tiny-widget diagnostics. Return an A/B/C verdict with evidence. No render-logic changes. Per project rule: no remediation until root cause is 100% confirmed from evidence.
Context:
Priority Guardian V1.0 (published, ChatGPT App Store) and MindSort AI (dev-mode, on hold) both show intermittent widget-non-render: the tool call (get_priorities / organize_thoughts) succeeds server-side and returns _meta.openai/outputTemplate, but the widget intermittently does not render, and — inferred from response-size proxy — the ChatGPT client does not issue resources/read. This is a production incident on a published app. Ecosystem reports correlate this with GPT-5.5-era MCP regressions, but that correlation is UNPROVEN for our apps and must not be assumed or asserted. PG and MindSort have separate copy-pasted resources.py (no shared module) — verify this against git show before relying on it.
Goal: Produce a binary verdict via observed log-facts (not size heuristics):

(A) Host/platform-side — tiny widget also fails → escalate to OpenAI, no code fix.
(B) App-payload/metadata — only one app fails → that app's response shape.
(C) Bundle-size-driven — tiny (<10KB) renders while real (357KB PG / 252KB MindSort) fails → shrink bundle.

Canonical guidance — read fresh before building (these are ChatGPT SDK apps):

"Priority Guard App Suite: Shared Backend — Architecture, Data Flow, Storage Strategy"
Compliance_Master.md (docs)
Openai_uiux.md (docs) — any UI the diagnostic widget renders MUST use OpenAI design tokens
ALL OPERATIONS...md docs — and read OPERATIONS_PREDEPLOY.md before committing/deploying anything
ADR_MCP Server implementation standard.md
Relevant ADRs (optional if applicable)
Data Retention Strategy (PDF) + Scalability & TAM — for production-readiness evaluation
If any doc is unreachable, unreadable, or shows a code/artifact mismatch, flag it and suggest a fix (living-artifact rule).

Phasing — minimize published-app risk:

Phase 1 (MindSort, dev-mode — do this first): All diagnostics on MindSort's dev connector, where tool/manifest changes are trivial and reversible with zero published-app risk. Because PG's and MindSort's resources.py are reported structurally identical, a Phase-1 size/host finding very likely transfers to PG.
Phase 2 (published PG — ONLY if Phase 1 is inconclusive or PG-specific confirmation is required): Adding/removing a tool on a published App Store app is a production manifest change (may require app update/refresh/re-scan). Full OPERATIONS_PREDEPLOY.md discipline; git stash before any working-tree overwrite; revert any diagnostic change immediately after.

Work items (requirements, not implementation — minimal code):

Explicit MCP request-type logging (both servers, but land/test on MindSort first). Log tools/list, tools/call, resources/list, resources/read, resources/templates/list as distinct structured events carrying the JSON-RPC method name, so "did the client fetch the resource" becomes a log-fact, not a size inference. Copy-and-adjust the existing logging pattern; do not restructure logging.
Tiny diagnostic widget + tool. Requirements:

Points to a <10KB widget resource.
Structural clone of the real tool's output — identical _meta shape/placement, identical outputTemplate mechanism, identical MIME (text/html;profile=mcp-app), identical registration path — differing ONLY in payload byte-size. Any other difference invalidates the size isolation.
Diagnostic tool must be side-effect-free: read-only (set readOnlyHint annotation), no user data, no backend calls, no persistence, clearly named as internal/diagnostic. This keeps it compliance-inert on a published app.
If it renders any UI, use OpenAI design tokens.


Capture current failing CallToolResult (fresh repro): full _meta (top-level vs nested), structuredContent, content, outputTemplate URI, MIME, size. Compare against the intended shape already verified in code. Do NOT block on a historical June-30 capture (retention + failed Loki queries make it likely unavailable) — compare current-failing vs intended-shape.
(Conditional) v13 cache-bust test — ONLY if items 1–3 are inconclusive, and ONLY in Phase 2 on PG. Temporarily bump PG widget URI to pg-dashboard-v13.html as a diagnostic, not a fix. Full OPERATIONS_PREDEPLOY.md treatment; revert immediately after.

Tests (unit and integration separated):

Unit: new logging emits correct distinct events per JSON-RPC method (mock each request type; assert event name/fields). Tiny-widget tool output is structurally identical to the real tool's _meta/outputTemplate, differing only in resource URI/size.
Integration: against a running dev server (established local Inspector setup), exercise tools/call → confirm resources/read logged as a distinct event; exercise the tiny-widget tool → confirm its resource is fetchable and logged.
DB integrity: no migration/column expected in this increment; if any is introduced, add DB-integrity tests before deploy. State explicitly if none.

Production-readiness (evaluate in context — diagnostic increment on a published SDK app):

Scalability: logging must add negligible per-request latency and no unbounded log volume (structured events only, no payload dumps).
GDPR/data-retention: logging must NOT capture user thought content, priority content, or PII — only method names, sizes, correlation IDs, tool names. Confirm against Data Retention Strategy. Critical for a published app.
Under load/latency: request-type logging runs per MCP request; confirm negligible overhead.

Deployment discipline: Touches two MCP servers, one published. Read OPERATIONS_PREDEPLOY.md before committing. git stash before any working-tree overwrite. Every reviewed round ends with a commit hash; review verifies against git show <hash>:<path>, not the working tree.
What NOT to do: No render-logic changes. No fix of any kind. No consolidating the duplicate resources.py files (flag only). No leaving diagnostic changes (tiny tool, v13 URI) in production. No assuming size or GPT-5.5 is the cause — tests must be able to exonerate each hypothesis.
Verdict step: After items 1–3 (Phase 1), state the binary outcome (A/B/C) with supporting log-facts. If A (host-side) → escalate to OpenAI, stop. If B or C → scope a bounded fix as a separate increment.

Two flags per your rules:

Undeclared duplication: PG and MindSort resources.py are reportedly identical copies with no shared module and no _dupl naming. This render bug may be the "demonstrated recurring churn" that justifies consolidation — but that's a separate decision, not this increment. Flagging for the living-artifact record; verify the "identical" claim against git show before acting.
What I did NOT verify this session (explicit): I did not re-read PG's or MindSort's resources.py this session — relying on Claude Code's "structurally identical, separate files" report, which must be verified against git show before the consolidation flag is acted on. I did not read Compliance_Master.md, ADR_MCP Server implementation standard.md, Openai_uiux.md, OPERATIONS_PREDEPLOY.md, the Shared Backend architecture doc, or the Data Retention Strategy this session — the briefing instructs Claude Code to read them fresh, but I have not personally validated the increment against them, so Claude Code must flag any mismatch. The "response-size = resources/read" basis for the whole incident remains an inference until work-item 1 replaces it with logged fact — which is why that item is first.

