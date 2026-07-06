BRIEFING — inc_96 (AUDIT, READ-ONLY): Production-guard coverage on the published apps (Unpack v2.0, Priority Guardian V1.0)
TOP INSTRUCTION: This is a read-only audit. Do NOT modify any code, config, or tests. Output is a findings report + commit hash of the audited state. If gaps are found, the fix is a separate per-app increment scoped afterward — nothing is fixed here. Per the 100%-root-cause rule, we do not know a gap exists until this audit confirms it.
Apps: Priority Guardian V1.0 and Unpack v2.0 — published ChatGPT App Store apps (both chatgpt-sdk). Focused is deprecated (skip). MindSort is on hold (already guarded, not in scope). ChatGPT-sdk canonical artifacts apply.
Why: inc_94/95 added dev-default-in-production fail-fast guards to MindSort/Clarity after two real incidents (2026-07-05 silent persistence failure; OAuth issuer discovery drift). Both incidents were the same class: an OAuth/infra-critical env var silently falling to its dev default in production. The unanswered, higher-severity question is whether the published, revenue apps carry the same exposure. A silent dev-default on a shipped app is a live production risk. This audit establishes the facts.
MOST-CRITICAL reading requirement: Read the relevant config/auth files in full — do not skim, infer, or assume PG/Unpack mirror Clarity. They have demonstrably diverged (this thread found PG's list_tools uses typed ToolAnnotations while Clarity used a raw dict; PG uses a different OAuth discovery shape than MindSort). So: do not assume PG/Unpack have the guards, and do not assume they lack them — read the actual code. If any required file cannot be read, state so explicitly rather than inferring.
Canonical guidance — READ FRESH before auditing (do not trust summaries, including mine):

ADR_005_platform_oauth_discovery_contracts.md — defines the three intentional discovery shapes. Each app must be judged against ITS OWN shape. Per prior context, PG-OpenAI uses the mixed-origin proxy shape (Shape #1), NOT MindSort's path-qualified /oauth/mindsort (Shape #2). Confirm each published app's correct expected OAuth values from ADR_005 directly. Do NOT flag PG/Unpack for using a legitimately-different shape — that would be a false gap.
"Priority Guard App Suite: Shared Backend — Architecture, Data Flow, Storage Strategy" — authority for each app's correct production values and the shared-module backend coupling.
Compliance_Master.md, ADR_MCP Server implementation standard.md — for what "correct production config" means per app.
ALL OPERATIONS...md.
If any doc is unreachable, unreadable, or mismatches the code, flag it and suggest a fix (living-artifact rule).

Scope (read-only) — for EACH app (PG V1.0, Unpack v2.0): locate and read the config module + auth module + wherever OAuth/infra-critical env vars resolve. Audit against the full production-guard set inc_94/95 established (not just the OAuth issuer):

Exact-match / dev-default guard on the OAuth issuer URL (judged against the app's ADR_005 shape — PG's expected value ≠ MindSort's).
Exact-match / dev-default guard on the JWKS URL (the JWT trust anchor — highest blast radius).
localhost-rejection guard on the backend URL (the 2026-07-05 incident class; note the shared-module coupling — does the app read backend URL via the same shared pattern?).
CORS_ALLOWED_ORIGINS required-in-production guard.
Unknown-ENV fail-fast guard.
Production predicate covers all aliases (production/prod/staging) — the prod-alias bypass was a real prior bug.
Startup logging of resolved OAuth/infra config (the observability that ends dashboard-vs-runtime ambiguity).

Audit output (report, NOT code) — per app:

For each of the 7 items: present / absent / partial, with file:line + git show <hash> evidence and the app's correct expected value per ADR_005.
Explicit list of unguarded production-critical vars = the gap set.
Any divergence from Clarity's structure relevant to a future fix (e.g., different config module layout, different env var names, shared vs. per-app resolution).
Note whether each app reads the backend URL via the shared module (CLARITY_BACKEND_URL coupling warning applies) or its own.

Do NOT: fix anything; add guards; modify config/tests; flag an app for using its correct-but-different ADR_005 shape; assume parity with Clarity in either direction.
Deliverable: commit hash of the audited state; per-app 7-item coverage table with file:line evidence; the gap set per app; explicit statement of any file you could NOT fully read (per the MOST-CRITICAL rule, an incomplete read must be disclosed, not silently inferred).
Production-readiness note: this is a read-only audit — no runtime/scalability/GDPR impact of its own. Its purpose is production-readiness of the published apps (do their guards protect against silent dev-default-in-production). Evaluate findings in the product/sdk-app context (published apps under load), not increment context.

Sequencing / priority: run this now — it's read-only, fast, and on your revenue apps. If it surfaces unguarded OAuth/backend vars on PG or Unpack, that fix increment jumps ahead of the remaining MindSort backlog items (guard aggregation, JWKS preflight) — a live gap on a shipped app outranks hardening the on-hold one. If both published apps are fully guarded, that's a clean result and the guard-pattern work is done.
What I have NOT verified this session (per your rule): I have not read PG's or Unpack's config/auth this session — the audit is read-first because I genuinely don't know their state. I have not read ADR_005's full per-app shape contracts this session; I'm relying on the KB summary (PG = Shape #1, MindSort = Shape #2), which is exactly why the briefing instructs Claude Code to read ADR_005 fresh and confirm each app's expected values rather than trust me. I cannot run git show/bash against the spaced path — Claude Code performs the git-pinned reads and returns file:line + hash evidence.
One strategic line, per your standing instruction: this is the increment that actually serves the business — it checks whether your published, earning apps are exposed to the failure class that already caused two incidents. It's the clean exit from the multi-session MindSort deep-dive: run the audit, fix whatever it finds on the revenue apps, and let that close the guard-pattern thread. After inc_96, your hours are best spent on the products' growth and monetization, not further hardening of an on-hold app.