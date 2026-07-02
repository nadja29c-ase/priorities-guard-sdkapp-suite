# Increment Briefing: inc_config_hardening_parity (PG-Claude)

**Title:** Back-port inc_05b config hardening from MindSort-Claude to PG-Claude
**Date:** 2026-07-02
**Scope:** ONLY `mcp_server/priority_guardian_claude/config.py` + that service's tests. NO discovery_dupl changes, NO backend, NO mindsort, NO OpenAI code. Rolls independently.
**Behavior contract:** Must be observably behavior-neutral for the correctly-configured deployed service. The increment only ADDS failure modes for MISconfiguration.

---

## Canonical guidance (read fresh before starting)

Claude SDK app — use the Claude-side canon:
- `doc/Claude_Compliance/claude_connectors_compliance_master.md`
- `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md`
- `doc/ADR_005_platform_oauth_discovery_contracts.md` (Shape #3 — the invariant these guards protect)
- `doc/CANONICAL_MCP_URLS.md` (canonical PG-Claude URL for docstring fixes)
- `doc/OPERATIONS_PREDEPLOY.md` — read before committing; check for additional pre-deploy tasks.

**Copy-and-Adjust source (roles now reversed):** `mcp_server/mindsort_claude/config.py` is the hardened reference — it received the full inc_05b + inc_05b-fix treatment (canonical ENV predicate, raise-on-unknown-ENV, `rstrip`, root-shape guard). PG-Claude was the original reference for inc_05b but never got the addendum hardening back-ported. Copy the hardened blocks from MindSort-Claude verbatim and adjust ONLY env-var names/prefixes in messages (`CLARITY_CLAUDE_*` → `PG_CLAUDE_*`). Do not rewrite, restructure, or improve anything not listed.

Reference for tests: `tests/unit/mcp_claude_mindsort/test_discovery.py` `TestConfigGuards` (guard tests 1–11) — the established subprocess technique (fresh interpreter, controlled env, assert on stderr substring so ModuleNotFoundError can't pass for the wrong reason).

---

## Problem (source-verified 2026-07-02 against both config files)

`priority_guardian_claude/config.py` is missing hardening that `mindsort_claude/config.py` now has. Concrete gaps, each with the bug it leaves open:

1. **No `.rstrip("/")` on `OAUTH_ISSUER_BASE`.** A Render value `https://www.priority-guard.com/` (trailing slash) leaks into `authorization_servers[0]` and `issuer` → non-canonical issuer on the connector currently in Anthropic review.
2. **No root-shape guard on `OAUTH_ISSUER_BASE`.** A Render value with a path (e.g. `/oauth/pg`) passes the existing same-origin guard (same scheme+netloc) → non-root `authorization_servers` → the exact pre-inc_05 Claude DCR failure class, silently.
3. **No raise-on-unknown-ENV.** A typo like `ENV=produciton` silently runs with all production guards disabled (localhost defaults could be advertised in what the operator believes is production).
4. **No canonical `_is_production_env` predicate.** Three inline `ENV in ("production", "prod", "staging")` tuples (get_env, INTERNAL_API_SECRET guard, localhost guard, CORS guard). Note: unlike pre-fix MindSort, PG's tuples already include `"prod"` — the Finding-1 bypass does NOT currently exist here. The predicate consolidation is for consistency and to prevent future tuple drift, not to close an active hole. State this accurately in comments; do not claim a bypass that isn't there.
5. **`IS_DEV = ENV == "dev"`** — inconsistent with the known-ENV set once it exists (`development`, `local`, `test`, `ci` would be neither dev nor production). Align to the MindSort pattern (`IS_DEV = not _is_production_env(ENV)`). Verify where IS_DEV is consumed before changing; state what you found.
6. **Stale docstring examples:** header says `pg-claude.priority-guard.com`; canonical is `https://mcp.priority-guard.com` per `doc/CANONICAL_MCP_URLS.md`. Fix all example URLs in the module docstring/comments. Comment-only.

Known dev/test ENV set must match MindSort's post-addendum set exactly: `{"dev", "development", "local", "test", "ci"}` — the inc_05b addendum's floor requirement applies here identically.

---

## Required changes (Copy and Adjust, Never Rewrite)

In `mcp_server/priority_guardian_claude/config.py`:
1. Copy MindSort-Claude's ENV block: `_PRODUCTION_ENV_VALUES` / `_DEV_ENV_VALUES` / `_is_production_env()` / raise-on-unknown-ENV. Placement discipline from the inc_05b addendum applies: predicate defined immediately after `ENV = os.getenv(...)` and BEFORE `get_env` (which will call it) — the file executes top-to-bottom at import.
2. Replace all inline production-ENV tuples with `_is_production_env(ENV)` (get_env, INTERNAL_API_SECRET guard, localhost guard, CORS guard).
3. Add `.rstrip("/")` to `OAUTH_ISSUER_BASE` at definition; add the root-shape guard (reject non-empty path beyond ""/"/", query, fragment) with a RuntimeError naming `PG_CLAUDE_OAUTH_ISSUER_BASE` and showing the offending value. Guard order mirrors MindSort: rstrip at definition → shape guard → existing same-origin guard → localhost guard, adjacent and deterministic.
4. Align `IS_DEV` per item 5 above.
5. Fix docstring/comment example URLs per item 6.

No changes to `discovery_dupl.py` (already sources `authorization_servers` from `OAUTH_ISSUER_BASE`).

---

## Tests

**Unit tests** (new file or extend the PG-Claude test module — follow existing layout; do not put these in the mindsort test file). Mirror MindSort's guard tests using the subprocess technique, adjusted to `PG_CLAUDE_*`. Each test states what bug would still pass it:
1. `ENV=produciton` (typo) → raises with "unknown ENV". *Catches:* raise-on-unknown absent.
2. `ENV=test` and `ENV=ci` → import clean. *Catches:* known-set floor violated (the inc_05b addendum regression).
3. `OAUTH_ISSUER_BASE` with path (`.../oauth/pg`) → raises with path-rejection message, `ENV=dev` to isolate the shape guard. *Catches:* origin-only guard (gap #2).
4. `OAUTH_ISSUER_BASE` with trailing slash → imports clean AND the exported value equals exactly `https://www.priority-guard.com` (no slash). *Catches:* missing rstrip (gap #1).
5. `ENV=prod` + unset OAuth env → raises via localhost guard. *Catches:* predicate regression dropping the `prod` alias (currently covered by tuples; this locks it).
6. Full production env happy path (`ENV=production`, all `PG_CLAUDE_*` vars correct incl. `PG_CLAUDE_INTERNAL_API_SECRET` and CORS) → imports clean AND `authorization_servers[0]` (via `discovery_dupl.oauth_protected_resource`) equals exactly `https://www.priority-guard.com`. *Catches:* guard false-positive on the real deployed combination.
All subprocess tests assert on stderr substring, not just returncode.

**Integration tests:** none required. The live discovery suite (`pytest -m live tests/integration/oauth_discovery/`) already verifies the deployed PG-Claude root-issuer shape; it must still pass unchanged post-deploy.

**Existing tests:** the oauth_discovery contract tests (incl. `test_pg_claude_production_shape` and the mount-coherence test, which inject `PG_CLAUDE_*` env) must remain green — they exercise this config under production-shaped values and will catch an over-strict guard.

---

## Deployment notes (deployer = Nadja; state in DoD)

- BEFORE redeploy, verify in the Render dashboard for `priority-guardian-claude-mcp`: `ENV` is exactly `production` and `PG_CLAUDE_OAUTH_ISSUER_BASE` is exactly `https://www.priority-guard.com` (no trailing slash, no path). The new guards turn any deviation into a startup failure — intended, but verify first rather than discovering at deploy.
- PG-Claude is in Anthropic review: this change is behavior-neutral for correct config (same discovery output), so deploying during review is acceptable; post-deploy, re-run the live discovery suite as confirmation.
- Read `doc/OPERATIONS_PREDEPLOY.md` before committing.

## Definition of done
- [ ] All five config changes applied; docstring URLs canonical; changes verified by re-reading the file.
- [ ] New guard tests pass; oauth_discovery contract tests pass; full unit suite baseline unchanged (the 5 known pre-existing failures, named in inc_oauth_discovery_contracts closure, and no new ones).
- [ ] Explicit statement of where IS_DEV is consumed and what changed.
- [ ] Explicit list of what was NOT verified.
- [ ] Deployer checklist above acknowledged; post-deploy live suite green.
