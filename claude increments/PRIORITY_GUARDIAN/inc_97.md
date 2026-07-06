BRIEFING — inc_97: Add unknown-ENV fail-fast + startup config logging to Priority Guardian V1.0
App: Priority Guardian V1.0 — published ChatGPT App Store app (mcp_server/priority_guardian/). ChatGPT-sdk canonical artifacts apply.
TOP INSTRUCTION: Requirements only, no implementation dictation. The reference pattern exists in mcp_server/clarity/config.py (inc_94's _KNOWN_ENV_VALUES/_is_production_env/unknown-ENV raise, and the resolved-config startup log). Copy-and-adjust to PG's structure and env-var names (PG_*, not CLARITY_*); do not restructure PG's config or invent values.
Why (verified against code at 81eb507): PG's ENV = os.getenv("ENV", "dev") has no validation. A typo (ENV=produciton) silently runs as dev, which disables every production guard PG has — the _prod_url_invariants block, CORS-required, INTERNAL_API_SECRET-required, RFC 8414 origin check. This is the highest-leverage gap: it's the meta-guard protecting all the others. Separately, PG has no startup logging of resolved config (dashboard-vs-runtime ambiguity — the class that cost multiple sessions diagnosing the MindSort discovery drift).
Scope: mcp_server/priority_guardian/config.py + tests. Two changes only:

Unknown-ENV fail-fast: validate ENV against a known set ({production, prod, staging} ∪ {dev, development, local, test, ci}); raise RuntimeError at import on unknown values. Mirror Clarity's _KNOWN_ENV_VALUES pattern. This prevents a typo from silently disabling PG's production guards.
Startup logging of resolved config: log resolved PG_JWKS_URL, MCP_SERVER_URL, MCP_RESOURCE_URL, OAUTH_ISSUER_URL, OAUTH_ISSUER_BASE, ENV at import. Confirm each is non-secret (public URLs) before logging — no PII, no INTERNAL_API_SECRET, no tokens.

Out of scope (do NOT do here):

Exact-match assert-known-good guards on OAuth/JWKS — PG already has localhost/http rejection + RFC 8414 origin guard + 7-var aggregation; the residual gap is narrow and requires PG-specific ADR_005 Shape #1 constants. Separate increment if pursued.
IS_DEV widening — verified NOT in the auth path; low priority, separate.
JWKS startup preflight — separate increment (shared with the MindSort backlog).
Do NOT touch MindSort/Clarity, mindsort_claude, Unpack, or backend.

Canonical guidance — READ FRESH before implementing:

"Priority Guard App Suite: Shared Backend — Architecture, Data Flow, Storage Strategy"
Compliance_Master.md; Openai_uiux.md (confirm no UI surface — config/logging only)
ADR_MCP Server implementation standard.md; ADR_005 (PG = Shape #1 — for confirming logged values, not for adding exact-match here)
ALL OPERATIONS...md; read OPERATIONS_PREDEPLOY.md before committing — this deploys to a published production app.
Flag any doc unreachable/mismatched (living-artifact rule).

Tests (unit separate from integration):

Unit: unknown ENV (produciton) raises at import; all known prod values (production/prod/staging) and dev values (dev/development/local/test/ci) import cleanly; startup log emits the resolved values (assert the actual VALUE appears, not just the field name — per the inc_94/95 lesson); logged values contain no secrets. Use the hermetic reimport-with-cleared-env pattern from test_config_guards.py (clear ambient env so tests don't depend on shell state). For each test, state what bug would still pass it.
Integration: PG server startup in a simulated production env with a valid config succeeds and logs resolved config; with an unknown ENV, fails fast at import.
DB integrity: none (state explicitly).

Production-readiness (evaluate in PUBLISHED-APP context, not just increment):

Scalability (Scalability & TAM): negligible — import-time only.
GDPR/data-retention (Data Retention Strategy): logged values are non-secret public URLs; no PII/secrets. Critical for a published app's logs.
Under load/latency: none — startup-only.
This ships to real users on a live App Store app — full pre-deploy discipline.

Deployment discipline: Read OPERATIONS_PREDEPLOY.md before committing. git stash before any working-tree overwrite. Reviewed round ends with a commit hash; review verifies against git show <hash>:<path>.
Deliverable: commit hash; test evidence (unknown-ENV raises, known values pass, log emits resolved values, no secrets); explicit "what I did NOT verify" list.

What I verified this session (against working tree at 81eb507, per your rules): PG config.py full (ENV unguarded; _prod_url_invariants 7-var aggregation present; RFC 8414 origin guard present; CORS + INTERNAL_API_SECRET guards present; IS_DEV narrow); PG mcp_auth.py full (fails closed, IS_DEV not in auth path, JWKS fetched lazily, three-audience deliberate). Could not run git show 81eb507 (bash can't reach spaced path) — read working tree; Claude Code must confirm git status clean at 81eb507. Did not grep for IS_DEV consumers outside auth (relevant only if you pursue Gap 4).
Corrections to the audit you should note: it framed PG as uniformly behind Clarity ("blocklist vs exact-match") — false. PG already aggregates multi-var failures (ahead of MindSort on the very concern we backlogged) and has an RFC 8414 origin guard the audit missed. The real gaps are narrower than reported: the high-value one is the unknown-ENV fail-fast, which is what inc_97 targets.
Strategic close, brief: this is the right increment — a real, verified, high-leverage gap on your published, revenue app, fixed with a proven pattern. It's the payoff of the whole guard thread: the pattern built on the on-hold app now protects the shipped one. Land inc_97, and the guard-coverage thread closes. Want me to hand this to Claude Code as-is, or adjust scope first?