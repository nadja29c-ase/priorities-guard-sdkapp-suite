BRIEFING 1 — inc_95: Extend dev-default-in-production guards to remaining OAuth-critical env vars (MindSort/Clarity)
App: MindSort-OpenAI (mcp_server/clarity/) — ChatGPT SDK app, on hold. ChatGPT canonical artifacts apply.
TOP INSTRUCTION: Requirements only, no implementation dictation. The reference implementation already exists in clarity/config.py (the inc_94 OAUTH_ISSUER_URL guard and the 2026-07-05 BACKEND_URL guard) — copy-and-adjust that pattern; do not restructure config.
Why: Two production incidents (2026-07-05 BACKEND_URL silent persistence failure; the recent OAUTH_ISSUER_URL discovery drift) are the same failure class: an OAuth/infra-critical env var silently falling to its dev default in production. CLARITY_JWKS_URL (dev default http://localhost:8000/oauth/pg/jwks) is the highest-blast-radius unguarded var — it's the JWT trust anchor (mcp_auth.py); if it falls to the dev default in production, auth fails closed → full outage; if pointed at a wrong live JWKS → validates against the wrong key set. CLARITY_ISSUER and CLARITY_AUDIENCE share the class at lower severity. This increment closes the class on Clarity.
Prerequisite decision (do NOT assume — determine against the codebase): guard SHAPE per var.
For each unguarded OAuth-critical var, decide the correct guard shape by reading its production value and semantics:

Exact-match assert-known-good (like OAUTH_ISSUER_URL) — only if the var has a single canonical fixed production value.
Dev-default-rejection (like BACKEND_URL's localhost check) — if the var can legitimately take multiple valid production forms; reject the known dev-default marker(s) instead of asserting one value.
Do not blindly apply exact-match to CLARITY_JWKS_URL — first confirm whether its production value is a single fixed string (https://www.priority-guard.com/oauth/mindsort/jwks) or can vary. State the chosen shape per var with rationale. Cross-check each expected value against ADR_005 and the Shared Backend architecture doc — do not invent values.

Scope: mcp_server/clarity/config.py + tests. Vars in scope: CLARITY_JWKS_URL (priority), CLARITY_ISSUER, CLARITY_AUDIENCE. Confirm whether any other production-critical var in this file lacks a guard and include it if the same class applies. Do NOT touch PG, Unpack, mindsort_claude, or backend.
Canonical guidance — read fresh before implementing (ChatGPT SDK app):

"Priority Guard App Suite: Shared Backend — Architecture, Data Flow, Storage Strategy" — authority for each var's correct production value/shape.
Compliance_Master.md
Openai_uiux.md (confirm no UI surface — config/logging only; note it)
ADR_MCP Server implementation standard.md
ADR_005_platform_oauth_discovery_contracts.md — for issuer/JWKS shape correctness.
ALL OPERATIONS...md; read OPERATIONS_PREDEPLOY.md before committing.
Flag any doc that is unreachable, unreadable, or mismatches the code (living-artifact rule).

Requirements:

Add production/staging fail-fast guards (gated on the existing _is_production_env()) for the in-scope vars, each using the shape determined above. Guards must NOT fire in dev/test (dev legitimately uses /oauth/pg-shaped defaults). Error messages must name the var, the expected value/marker, and reference the incident class + ADR_005 where relevant — mirroring the existing guards' message style.
Extend the inc_94 startup logging to include the newly guarded resolved values (e.g. jwks_url) only if non-secret — confirm each is a public URL before logging; never log secrets/PII.

Tests (unit separate from integration):

Unit: for each guarded var — raises in production/staging on dev-default AND on an arbitrary wrong value (prove assert-known-good where that shape is used); passes on the correct value; does NOT fire in dev/test. For each test, state what bug would still pass it. Fix the coverage gap inc_94 review found: any logging test must assert the resolved value appears, not merely the field name.
Integration: server startup in a simulated production env with a dev-default JWKS URL fails fast at startup (not at first auth call).
DB integrity: none in this increment (state explicitly).

Production-readiness (in context — small config increment on a ChatGPT-SDK server):

Scalability: negligible (import-time checks).
GDPR/data-retention: logged values must be non-secret public URLs only; no PII.
Under load/latency: none (startup-only).

Deployment discipline: Read OPERATIONS_PREDEPLOY.md before committing. git stash before any working-tree overwrite. Reviewed round ends with a commit hash; review verifies against git show <hash>:<path>.
What NOT to do: No universal cross-app rule. No touching PG/Unpack/backend/Claude. No exact-match on a var that legitimately varies. No restructuring config.
Deliverable: commit hash; per-var chosen guard shape + rationale; test evidence (raise-on-wrong incl. arbitrary value where exact-match, pass-on-correct, no-fire-in-dev); explicit "what I did NOT verify" list.

additional info:

is this valid feedback? 

Yes — this is correct, production-ready in scope, and compliant.
Verdict: approve.
Key reasons:

Correctly separates fix vs audit.
Does not assume PG/Unpack have the same gap.
Avoids copying MindSort-specific /oauth/mindsort logic into other apps.
Requires app-specific guard shapes based on ADR_005.
Keeps inc_95 scoped to Clarity only.
Keeps inc_96 read-only, which is the right first step for published apps.
Production-readiness is properly scoped: import-time guards, no user data, no runtime latency. One small improvement: For inc_95, make CLARITY_JWKS_URL exact-match unless canonical docs explicitly say it can vary. JWKS is normally a fixed app-specific endpoint:
https://www.priority-guard.com/oauth/mindsort/jwks
So default should be exact-match, not “maybe varies.”
Final: run inc_96 first or in parallel. It is higher-value because it checks the published apps.

Show less
The feedback is valid on the whole, and its one improvement is directionally right but stated in a way that would violate your own most-critical rule if I encoded it literally. Let me separate those.

Where ChatGPT is right: the fix/audit separation, no-assumption on PG/Unpack, app-specific guard shapes per ADR_005, read-only audit as the correct first step for published apps, and inc_96-first because it touches revenue. All confirmed. Approve those.

The JWKS point — right instinct, wrong instruction. ChatGPT says: "make CLARITY_JWKS_URL exact-match unless canonical docs explicitly say it can vary — JWKS is normally a fixed endpoint, so default to exact-match." The conclusion is probably correct (a single app's JWKS URL usually is one fixed value). But the framing — "default to exact-match unless docs say otherwise" — is exactly the assume-then-verify inversion your rules forbid. It's saying "assume the strict shape and only reconsider if a doc contradicts." Your rule is the opposite: determine the correct value against the real config/production, THEN choose the shape. The difference is not pedantic — it's the whole discipline that took this thread four sessions to honor. "JWKS is normally fixed" is a prior, not a verified fact about your CLARITY_JWKS_URL.

Concretely: I don't actually know your production JWKS URL is https://www.priority-guard.com/oauth/mindsort/jwks. It's the plausible value (it matches the /oauth/mindsort issuer shape), and your earlier logs did show JWKS being fetched from https://www.priority-guard.com/oauth/mindsort/jwks. So there's real evidence it's that fixed value — which makes exact-match the likely correct shape. But "likely" plus "logs showed it once" is grounds for Claude Code to confirm it's a single canonical value and then apply exact-match, not grounds for me to pre-decide exact-match in the briefing. The briefing already says "determine the shape against the real value" — that's the correct instruction and I'm keeping it. I'll add ChatGPT's substance as guidance, not as a default:

JWKS guard-shape note: a single app's JWKS endpoint is typically one fixed URL, and production logs this session showed CLARITY_JWKS_URL resolving to https://www.priority-guard.com/oauth/mindsort/jwks. So exact-match is the expected shape — BUT confirm the canonical production value against the Shared Backend doc / ADR_005 and the running config before applying it. Choose dev-default-rejection instead ONLY if you find evidence the value legitimately varies. Do not default to a shape without confirming the value.

That captures ChatGPT's correct point (exact-match is the likely answer) without encoding the assume-first framing.

So: the feedback is valid, its improvement is worth folding in as evidence-weighted guidance rather than a pre-decided default, and nothing else changes. Both briefings stand with that one addition to inc_95's JWKS section. Priority unchanged: inc_96 (published-apps audit) first or parallel — it's the revenue-touching one.