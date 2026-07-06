BRIEFING — inc_94: Startup logging + fail-fast guard for resolved OAuth issuer config (MindSort/Clarity)
App: MindSort-OpenAI (mcp_server/clarity/) — ChatGPT SDK app, on hold. ChatGPT canonical artifacts apply.
TOP INSTRUCTION: This is a config/observability increment. Do NOT change OAuth behavior for valid config. Do NOT claim the original drift cause is proven — it is not (see below). No implementation dictation; requirements only.
Why (cause NOT proven): Production MindSort discovery briefly served the dev-default OAuth issuer (/oauth/pg) instead of production (/oauth/mindsort), despite the Render env var being correctly set to https://www.priority-guard.com/oauth/mindsort. The discrepancy resolved before the runtime-resolved value was captured, so the mechanism is unconfirmed (candidates: stale instance, restart timing, env propagation). This increment does not explain it — it makes the failure class impossible to serve silently: a production process running with a wrong/dev-default OAuth issuer must fail fast at startup, and resolved OAuth config must be logged so a dashboard-vs-runtime mismatch is never a guessing game again.
Scope: mcp_server/clarity/config.py + tests only. Do NOT touch PG, mindsort_claude, or backend.
Canonical guidance — READ FRESH before implementing (ChatGPT SDK app):

"Priority Guard App Suite: Shared Backend — Architecture, Data Flow, Storage Strategy"
Compliance_Master.md (docs)
Openai_uiux.md (docs) — confirm this increment has NO UI/SDK surface (config/logging only); note that it doesn't
ADR_MCP Server implementation standard.md
ADR_005_platform_oauth_discovery_contracts.md — governing: defines the three intentional discovery shapes; the guard MUST NOT encode a universal "path-qualified" rule. Confirm Clarity's expected production issuer and that dev-default detection doesn't violate any shape.
ALL OPERATIONS...md; read OPERATIONS_PREDEPLOY.md before committing.
If any doc is unreachable, unreadable, or mismatches the code, flag it and suggest a fix (living-artifact rule).

Reference pattern (read and mirror it — do not assume its form): config.py already has a fail-fast guard for BACKEND_URL that raises in production when the value contains localhost (added after the 2026-07-05 silent-persistence incident), plus the _is_production_env() predicate. Read both and reuse them. Mirror this pattern; do not invent a new one.
Work items (requirements — minimal code):

Startup/import-time logging of resolved OAuth config — log resolved OAUTH_ISSUER_URL, MCP_SERVER_URL, MCP_RESOURCE_URL. Confirm these are non-secret URLs before logging (no secrets/PII). Use the existing structlog pattern. This is the observability that ends dashboard-vs-runtime ambiguity.
Fail-fast production/staging guard on OAUTH_ISSUER_URL, gated on _is_production_env():

In production/staging, the resolved value MUST equal Clarity's expected production issuer https://www.priority-guard.com/oauth/mindsort; raise (refuse to start) otherwise. Assert the known-correct value — this catches ANY wrong value, not merely a blocklist of known dev-defaults.
The error message should specifically name the observed drift vectors as defense-in-depth: localhost, http://localhost:8000/oauth/pg, bare https://www.priority-guard.com, https://www.priority-guard.com/oauth/pg — and state the expected production value.
In dev/test ENV the guard MUST NOT fire (dev legitimately uses the /oauth/pg default).
This exact-value assertion is app-specific to Clarity. When this pattern is later reused on other apps, each asserts ITS OWN expected issuer per ADR_005 — do NOT universalize a "must-be-path-qualified" rule.


Verify shim interaction (prerequisite for correct guard placement): confirm whether mcp_auth_dupl.py or any import-order override rebinds OAUTH_ISSUER_URL after config.py import. If it does, the guard and logging must validate the served (post-shim) value, not the pre-shim import value — otherwise the guard passes while production serves the wrong value. Report findings; place the guard where it sees the served value.

Tests (unit separated from integration):

Unit: guard raises in production/staging when OAUTH_ISSUER_URL is any non-expected value (test localhost, /oauth/pg, bare domain, AND an arbitrary third wrong value to prove it's assert-known-good not blocklist); guard passes on https://www.priority-guard.com/oauth/mindsort; guard does NOT fire in dev/test ENV (dev /oauth/pg allowed); logging emits the three resolved URLs with no secrets. For each test, state what bug would still pass it.
Integration: server startup in a simulated production ENV with a dev-default issuer fails fast at startup (not at first request); startup with the correct value succeeds and logs the resolved config.
DB integrity: no migration/column in this increment; state so explicitly.

Production-readiness (evaluate in context — small config/observability increment on a ChatGPT-SDK server):

Scalability (Scalability & TAM): negligible — import-time check + startup log, no per-request cost.
GDPR/data-retention (Data Retention Strategy): logged URLs must contain NO secrets/PII — confirm the three URLs are non-secret; no user data touched.
Under load/latency: none — startup-only.

Deployment discipline: ChatGPT-SDK server config change. Read OPERATIONS_PREDEPLOY.md before committing; git stash before any working-tree overwrite. Reviewed round ends with a commit hash; review verifies against git show <hash>:<path>.
What NOT to do: No universal "path-qualified" rule (violates ADR_005 multi-shape design). No modifying PG/Unpack/backend/mindsort_claude. No stating the original drift cause as confirmed. No restructuring config beyond the guard + logging.
Deliverable: commit hash; test evidence that the guard raises on wrong values (incl. an arbitrary third) and passes on the correct value; the shim-interaction finding (WI 3); explicit "what I did NOT verify" list.
Out of scope but TRACKED as the immediate next task (do NOT do in inc_94): verify whether PG (priority_guardian/config.py) and Unpack have equivalent app-specific dev-default OAuth-issuer guards. If absent, that is a gap on published apps (Unpack v2.0, Priority Guardian V1.0) and takes priority over further on-hold-app work. Each app's guard asserts its own expected issuer per ADR_005 — do not copy Clarity's /oauth/mindsort value.

What I did NOT verify this session (per your rule): I have not personally read, this session — the exact form of the existing BACKEND_URL guard / _is_production_env(); ADR_005's full shape contracts; whether mcp_auth_dupl.py rebinds OAUTH_ISSUER_URL; PG's/Unpack's configs. The briefing requires Claude Code to read and verify each; I have not validated the increment against them myself. I also cannot run Render Shell / curl / git-show against the spaced repo path — Claude Code executes those and returns evidence + hash.
One strategic line, then I'll stop repeating it: inc_94 hardens an on-hold app. Its real value is the tracked follow-up — checking whether Unpack v2.0 and Priority Guardian V1.0 (your published, revenue apps) share this unguarded gap. Land inc_94, then make that check the next increment, not a sinking backlog item. After that, the disciplined move for Fulfilling Productivity is to put your hours on the shipped products and monetization — the multi-session MindSort deep-dive has extracted its durable win (this guard pattern); don't let the parked app keep absorbing the work.
